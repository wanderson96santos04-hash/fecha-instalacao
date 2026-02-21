from .routes import bp

def register(app):
    """
    Integração simples (sem mexer no que já existe):
        from app.modules.acquisition import register as register_acquisition
        register_acquisition(app)
    """
    app.register_blueprint(bp)
