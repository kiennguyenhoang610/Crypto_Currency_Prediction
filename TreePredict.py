import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor

def PredictValue(stock_type="BTC", days=1):
    # 1. Read data dynamically based on coin type
    filename = f'{stock_type}-USD.csv'
    df = pd.read_csv(filename)
    df2 = df[['Close']].copy()

    # 2. Process prediction logic based on the number of days
    # The model will learn the relationship between today's price and the price 'days' into the future
    df2['Prediction'] = df2['Close'].shift(-days)
    
    X = np.array(df2[['Close']])
    X_train_full = X[:-days] # Data used for training
    y_train_full = np.array(df2['Prediction'])[:-days]

    # 3. Train models (Use all available data to achieve the highest accuracy for the Demo)
    tree = DecisionTreeRegressor(random_state=42).fit(X_train_full, y_train_full)
    rf = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train_full, y_train_full)

    # 4. Get the 6 most recent price points to use as background data for the chart (Current Context)
    current_context = df2['Close'].tail(6).values
    
    # 5. Predict the price for the next 'days' based on today's final price
    last_price = np.array([[df2['Close'].iloc[-1]]])
    tree_future_val = tree.predict(last_price)[0]
    rf_future_val = rf.predict(last_price)[0]

    # 6. Return a 7-element array: 6 past elements + 1 predicted element at the end
    tree_output = np.append(current_context, tree_future_val)
    rf_output = np.append(current_context, rf_future_val)

    return tree_output, rf_output