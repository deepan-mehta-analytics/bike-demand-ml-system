# ── Imports ───────────────────────────────────────────────────────────────────
import logging                                                          # structured logging to stdout (Cloud Logging reads stdout)
import requests                                                         # HTTP client for REST-based GCP API calls
import google.auth                                                      # ADC credential resolution (uses SA in Cloud Run, gcloud in dev)
import google.auth.transport.requests as google_requests               # transport object required to refresh ADC tokens

from google.cloud import artifactregistry_v1                            # Artifact Registry client — list Docker images + sizes
from google.cloud import compute_v1                                     # Compute Engine client — list VM instances across all zones
from google.cloud import bigquery                                       # BigQuery client — table metadata + SQL queries
from google.cloud import storage                                        # GCS client — list buckets and blob sizes

logger = logging.getLogger(__name__)                                    # module-level logger; caller configures basicConfig


# ── Auth Helper ────────────────────────────────────────────────────────────────

def _get_auth_headers() -> dict:                                        # returns a Bearer token Authorization header for REST calls
    """Refresh ADC credentials and return Authorization header dict."""
    creds, _ = google.auth.default()                                    # resolve ADC — SA in Cloud Run, gcloud credentials in dev
    auth_req = google_requests.Request()                                # transport object required by the refresh call
    creds.refresh(auth_req)                                             # ensure token is not expired before use
    return {"Authorization": f"Bearer {creds.token}"}                  # standard Bearer token header for GCP REST APIs


# ── Artifact Registry ─────────────────────────────────────────────────────────

def check_artifact_registry(project: str, location: str, repo: str) -> dict:
    """List all Docker images in the repo. Returns pkg_versions dict and total_gb float."""
    client = artifactregistry_v1.ArtifactRegistryClient()              # client uses ADC automatically — no explicit credential needed
    parent = f"projects/{project}/locations/{location}/repositories/{repo}"  # resource path for the registry repo
    request = artifactregistry_v1.ListDockerImagesRequest(parent=parent)     # paginated list request

    pkg_versions = {}                                                   # {package_name: version_count} — one entry per unique image name
    total_bytes = 0                                                     # running byte total across all images in the repo

    for img in client.list_docker_images(request=request):             # auto-paginates through all images
        # img.name: "projects/.../repositories/bike-demand-repo/dockerImages/bike-demand-api@sha256:abc"
        img_path = img.name.split("/dockerImages/")[-1]                # strip the resource prefix, keep "image@sha256:..."
        pkg_name = img_path.split("@")[0]                              # package name is the part before the digest separator
        pkg_versions[pkg_name] = pkg_versions.get(pkg_name, 0) + 1    # increment version count for this package
        total_bytes += img.image_size_bytes                             # accumulate compressed image size in bytes

    total_gb = total_bytes / 1_000_000_000                             # convert bytes to GB (decimal, not binary)
    logger.info(f"Registry: {sum(pkg_versions.values())} images, {total_gb:.2f} GB")
    return {"pkg_versions": pkg_versions, "total_gb": total_gb}        # caller passes this dict into evaluate_thresholds


# ── Compute Engine ────────────────────────────────────────────────────────────

def check_compute(project: str) -> dict:
    """List all running Compute Engine VMs across all zones. Returns running_vms list."""
    client = compute_v1.InstancesClient()                              # uses ADC automatically
    request = compute_v1.AggregatedListInstancesRequest(project=project)  # aggregated = single call covers all zones
    agg_list = client.aggregated_list(request=request)                 # returns an iterator of (zone, instances_in_zone) pairs

    running_vms = []                                                    # names of VMs currently in RUNNING state
    for _zone, instances_in_zone in agg_list:                          # iterate all zone groups; underscore = zone string not needed
        if instances_in_zone.instances:                                 # skip empty zone groups (most zones have no VMs)
            for instance in instances_in_zone.instances:               # check each VM in this zone
                if instance.status == "RUNNING":                       # only RUNNING VMs are live cost; TERMINATED/STOPPED are not
                    running_vms.append(instance.name)                  # name is sufficient for the alert message

    logger.info(f"Compute: {len(running_vms)} running VMs")
    return {"running_vms": running_vms}                                 # empty list = healthy


# ── Vertex AI (REST) ──────────────────────────────────────────────────────────

def check_vertex(project: str, location: str) -> dict:
    """List Vertex AI endpoints via REST. Returns endpoints list (avoids heavy aiplatform dep)."""
    headers = _get_auth_headers()                                       # fresh Bearer token for REST call
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1"
        f"/projects/{project}/locations/{location}/endpoints"
    )                                                                   # Vertex AI Endpoints REST endpoint (location-scoped)
    resp = requests.get(url, headers=headers, timeout=30)              # read-only GET; 30s timeout for slow regions
    resp.raise_for_status()                                             # raise HTTPError on 4xx/5xx so caller catches it
    endpoints = resp.json().get("endpoints", [])                       # "endpoints" key absent = no endpoints = empty list
    logger.info(f"Vertex: {len(endpoints)} endpoints")
    return {"endpoints": endpoints}                                     # empty list = healthy


# ── BigQuery — storage metadata ────────────────────────────────────────────────

def check_bigquery(project: str) -> dict:
    """Sum storage bytes across all BQ datasets in the project. Returns total_gb float."""
    client = bigquery.Client(project=project)                          # uses ADC; SA needs bigquery.dataViewer
    total_bytes = 0                                                     # running byte total across all tables

    for ds_item in client.list_datasets():                             # iterate dataset list items (lightweight metadata only)
        dataset_id = ds_item.dataset_id                                # e.g. "billing_export" or "station_snapshots"
        for tbl_item in client.list_tables(dataset_id):                # iterate table list items for each dataset
            table_ref = f"{project}.{dataset_id}.{tbl_item.table_id}" # fully qualified table reference for get_table()
            try:
                table = client.get_table(table_ref)                    # fetch full table metadata — includes num_bytes field
                total_bytes += table.num_bytes or 0                    # num_bytes is None for views or streaming-only tables
            except Exception as e:
                logger.warning(f"BQ table metadata failed for {table_ref}: {e}")  # one bad table must not abort the whole check

    total_gb = total_bytes / 1_000_000_000                             # convert bytes to GB
    logger.info(f"BigQuery: {total_gb:.2f} GB total storage")
    return {"total_gb": total_gb}                                       # caller passes into evaluate_thresholds


# ── BigQuery — MTD billing spend ───────────────────────────────────────────────

BILLING_TABLE = (
    "bike-demand-ml-system.billing_export"
    ".gcp_billing_export_v1_015DB7_CE9C3D_2F5093"
)                                                                       # billing export table; hyphens → underscores in table name

def check_spend_mtd(project: str) -> dict:
    """Query billing export for month-to-date spend in INR. Returns mtd_cost_inr float."""
    client = bigquery.Client(project=project)                          # SA needs bigquery.dataViewer on billing_export + jobUser
    query = f"""
        SELECT ROUND(SUM(cost), 2) AS mtd_cost_inr
        FROM `{BILLING_TABLE}`
        WHERE DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
    """                                                                 # sums all services for the current calendar month
    try:
        rows = list(client.query(query).result())                      # blocks until complete; fast for small billing tables
        mtd_cost = float(rows[0]["mtd_cost_inr"]) if rows and rows[0]["mtd_cost_inr"] is not None else 0.0
    except Exception as e:
        logger.warning(f"Billing query failed (table may not exist yet): {e}")  # table is absent until first export runs
        mtd_cost = 0.0                                                  # treat as zero spend — avoids false alerts on new projects
    logger.info(f"Spend MTD: ₹{mtd_cost:.0f}")
    return {"mtd_cost_inr": mtd_cost}                                   # caller passes into evaluate_thresholds


# ── GCS ───────────────────────────────────────────────────────────────────────

def check_gcs(project: str) -> dict:
    """Sum blob sizes per GCS bucket. Returns bucket_sizes dict {bucket_name: size_gb}."""
    client = storage.Client(project=project)                           # uses ADC; SA needs storage.objectViewer
    bucket_sizes = {}                                                   # {bucket_name: total_gb}

    for bucket in client.list_buckets():                               # iterate all buckets owned by the project
        total_bytes = sum(                                              # sum blob.size across all blobs; list_blobs auto-paginates
            blob.size for blob in client.list_blobs(bucket.name)
            if blob.size is not None                                    # blob.size is None for directory placeholder objects
        )
        bucket_sizes[bucket.name] = total_bytes / 1_000_000_000       # convert bytes to GB
        logger.info(f"GCS: {bucket.name} = {bucket_sizes[bucket.name]:.2f} GB")

    return {"bucket_sizes": bucket_sizes}                              # empty dict = no buckets = healthy


# ── Cloud Run (REST) ──────────────────────────────────────────────────────────

def check_cloud_run(project: str, location: str) -> dict:
    """List Cloud Run services via REST v2 API. Returns list of {name, min_instances} dicts."""
    headers = _get_auth_headers()                                       # fresh Bearer token for REST call
    url = f"https://run.googleapis.com/v2/projects/{project}/locations/{location}/services"
    resp = requests.get(url, headers=headers, timeout=30)              # read-only GET; 30s timeout
    resp.raise_for_status()                                             # raise on 4xx/5xx so caller catches it

    services = []                                                       # list of {name, min_instances} dicts
    for svc in resp.json().get("services", []):                        # "services" absent = no services deployed
        name = svc.get("name", "<unknown>").split("/services/")[-1]   # strip resource path prefix to get short service name
        scaling = svc.get("scaling", {})                               # scaling config may be absent on older services
        min_instances = scaling.get("minInstanceCount", 0)             # 0 = scale-to-zero; >0 = always-on (paid)
        services.append({"name": name, "min_instances": min_instances})

    logger.info(f"Cloud Run: {len(services)} services found")
    return {"services": services}                                       # caller passes into evaluate_thresholds
