import pandas as pd

def load_data(path):
    """
    Load dataset from CSV
    """
    df = pd.read_csv(path)
    return df


def create_features(df):
    """
    Basic feature engineering
    """

    # Convert date to datetime
    df["DATE"] = pd.to_datetime(df["DATE"], dayfirst=True)

    # Extract time-based features
    df["year"] = df["DATE"].dt.year
    df["month"] = df["DATE"].dt.month
    df["day"] = df["DATE"].dt.day
    df["dayofweek"] = df["DATE"].dt.dayofweek

    return df


def get_feature_target(df):
    """
    Split into X (features) and y (target)
    """

    target = "RENTED_BIKE_COUNT"

    # Separate features and target
    X = df.drop(columns=[target, "DATE"])
    y = df[target]

    # Convert categorical columns into numeric (one-hot encoding)
    X = pd.get_dummies(X)

    return X, y

# -------------------------------
# TEST BLOCK (runs only when file is executed directly)
# -------------------------------

if __name__ == "__main__":
    # Load dataset
    df = load_data("data/raw/seoul_bike_sharing.csv")

    # Create features
    df = create_features(df)

    # Split data
    X, y = get_feature_target(df)

    # Print basic checks
    print("Shape of X:", X.shape)
    print("Shape of y:", y.shape)
    print(X.head())