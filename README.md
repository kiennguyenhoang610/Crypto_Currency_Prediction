# 🪙 Crypto Currency Prediction System
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/flask-2.0+-green.svg)
![ML](https://img.shields.io/badge/Machine%20Learning-DecisionTree%20%26%20RandomForest-orange)

An intelligent web-based system for predicting Bitcoin (BTC) price movements using advanced machine learning models and real-time visualization.

## 🚀 Features
### 👤 End User
- **Interactive Dashboards**: Real-time price charts using Chart.js.
- **Dual-Model Prediction**: Compare forecasts from Decision Tree and Random Forest.
- **Market Sentiment**: Visual indicators (Green/Red) for predicted price changes.

### 🧪 Data Scientist
- **Model Retraining Pipeline**: Upload new CSV datasets to update models on the fly.
- **Performance Metrics**: Monitor R², RMSE, and MAE scores for each training session.
- **Model Registry**: Download and manage different versions of `.pkl` model artifacts.

### 🛡️ System Admin
- **Role-Based Access Control (RBAC)**: Secure management of Users, Scientists, and Admins.
- **Audit Logs**: Track every prediction, login, and system change.
- **System Monitoring**: View daily request traffic and model health.

## 🛠 Technology Stack
- **Backend**: Flask (Python)
- **Machine Learning**: Scikit-learn (Random Forest Regressor, Decision Tree Regressor)
- **Data Processing**: Pandas, NumPy
- **Frontend**: HTML5, CSS3, JavaScript (Chart.js, FontAwesome)
- **Storage**: JSON-based state management with thread-safe locking

## 💻 Getting Started

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/kiennguyenhoang610/Crypto_Currency_Prediction.git](https://github.com/kiennguyenhoang610/Crypto_Currency_Prediction.git)
   cd Crypto_Currency_Prediction

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt

4. **Run the application:**
   ```bash
   python app.py
The server will start at http://127.0.0.1:5001

## 📊 Mathematical Foundation
The system evaluates model performance using **Root Mean Squared Error (RMSE)** and **R-squared ($R^2$)**:

$$RMSE = \sqrt{\frac{1}{n} \sum_{i=1}^{n} (y_i - \hat{y}_i)^2}$$

The models utilize a **Lag-Feature Engineering** approach, where the price at day $T$ is predicted using historical data from $T-1$ to $T-6$.
   
