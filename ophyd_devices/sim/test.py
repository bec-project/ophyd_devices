import lmfit
import inspect


class LmfitModelMixin:

    # def __init__(self):
    #     self.model = lmfit.models.GaussianModel()
    #     self.params = self.model.make_params()
    #     self.params["center"].set(value=0)
    #     self.params["amplitude"].set(value=1)
    #     self.params["sigma"].set(value=1)

    @staticmethod
    def available_models() -> dict:
        """
        Get available models from lmfit.models.

        Exclude Gaussian2dModel, ExpressionModel, Model, SplineModel.
        """
        avail_models = {}
        for name, model_cls in inspect.getmembers(lmfit.models):
            try:
                is_model = issubclass(model_cls, lmfit.model.Model)
            except TypeError:
                is_model = False
            if is_model and name not in [
                "Gaussian2dModel",
                "ExpressionModel",
                "Model",
                "SplineModel",
            ]:
                avail_models[name] = model_cls
        return avail_models

    def create_properties(self):
        """
        Create properties for model parameters.
        """
        for name in self.available_models():
            setattr(self, name, param)

    @staticmethod
    def get_model(model: str) -> lmfit.Model:
        """Get model for given string."""
        if isinstance(model, str):
            model = getattr(lmfit.models, model, None)
        if not model:
            raise ValueError(f"Model {model} not found.")
        return model
