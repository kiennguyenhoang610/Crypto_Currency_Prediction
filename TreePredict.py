def PredictValue(stock_type="BTC", days=1):
    from app import app
    from services.model_service import ModelService

    with app.app_context():
        service = ModelService(app.config)
        result = service.predict(stock_type, days=days)
        return result["dt_series"], result["rf_series"]
