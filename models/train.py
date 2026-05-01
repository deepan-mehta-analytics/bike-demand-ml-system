# Import required libraries
import pandas as pd  # for data handling
from sklearn.model_selection import train_test_split  # to split data
from sklearn.linear_model import LinearRegression  # simple baseline model
from sklearn.metrics import mean_squared_error  # evaluation metric
import joblib  # used to save and load trained machine learning models

# Import feature functions from features.py
from models.features import load_data, create_features, get_feature_target
from sklearn.preprocessing import StandardScaler  # used to scale features to same range
from sklearn.ensemble import RandomForestRegressor  # non-linear model for better performance


# -------------------------------
# MAIN TRAINING PIPELINE
# -------------------------------
if __name__ == "__main__":

    # Step 1: Load data
    df = load_data("data/raw/seoul_bike_sharing.csv")

    # Step 2: Create features
    df = create_features(df)

    # Step 3: Split into X (features) and y (target)
    X, y = get_feature_target(df)

    # -------------------------------
    # SAVE FEATURE SCHEMA
    # -------------------------------

    # Save feature column names so prediction input can be aligned correctly
    joblib.dump(X.columns.tolist(), "models/feature_columns.pkl")  # store column structure


    # Step 4: Train-test split (80-20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Step 5: Initialize scaler to normalize feature values
    scaler = StandardScaler()  # creates a scaling object to standardize features

    # Step 6: Fit scaler on training data and transform it
    X_train = scaler.fit_transform(X_train)  # learns mean/std from training data and scales it

    # Step 7: Apply same transformation to test data (no fitting here)
    X_test = scaler.transform(X_test)  # ensures test data uses same scaling parameters

    # Step 8: Initialize model
    # model = LinearRegression()  # create linear regression model
    model = RandomForestRegressor(n_estimators=100, random_state=42)  # ensemble model with 100 trees
    # Step 9: Train model using scaled training data
    model.fit(X_train, y_train)  # fits model to scaled features
    # -------------------------------
    # SAVE TRAINED MODEL
    # -------------------------------

    # Save trained model to disk so it can be reused later without retraining
    joblib.dump(model, "models/random_forest_model.pkl")  # saves model as a file
    joblib.dump(scaler, "models/standard_scaler.pkl")   # saves scaler as a file
    print("Model and scaler saved successfully!")  # confirmation message
    

    # Step 10: Make predictions on scaled test data
    predictions = model.predict(X_test)  # generates predictions

    # Step 11: Evaluate model
    mse = mean_squared_error(y_test, predictions)

    # Step 12: Print result
    print("Mean Squared Error:", mse)
    
    # Calculate Root Mean Squared Error (RMSE) by taking square root of MSE
    rmse = mse ** 0.5  # RMSE gives error in same units as target variable

    # Print RMSE value for better interpretability
    print("RMSE:", rmse)  # Displays how far predictions are from actual values on average

    # -------------------------------
    # FEATURE IMPORTANCE (Model Explainability)
    # -------------------------------

    # Extract feature importance scores from trained Random Forest model
    importances = model.feature_importances_  # gives importance score for each feature

    # Get feature names from dataset
    feature_names = X.columns  # original column names before scaling

    # Create a DataFrame to pair feature names with their importance
    feature_importance_df = pd.DataFrame({
        "feature": feature_names,          # column names
        "importance": importances          # importance scores
    })

    # Sort features by importance (highest first)
    feature_importance_df = feature_importance_df.sort_values(by="importance", ascending=False)

    # Print top 10 most important features
    print("\nTop 10 Feature Importances:")
    print(feature_importance_df.head(10))  # display top contributors