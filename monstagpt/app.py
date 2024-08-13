import logging
from logging.handlers import SMTPHandler
from lib.custom_logging_handler import CustomLoggingHandler
import stripe
from celery import Celery
from flask import Flask
from flask import render_template
from flask import request
from flask_login import current_user
from werkzeug.debug import DebuggedApplication
from werkzeug.middleware.proxy_fix import ProxyFix
from kombu import Exchange, Queue

from cli import register_cli_commands
from monstagpt.blueprints.admin.views import admin
from monstagpt.blueprints.billing.template_processors import current_year
from monstagpt.blueprints.billing.template_processors import format_currency
from monstagpt.blueprints.billing.template_processors import split_after_underscore
from monstagpt.blueprints.billing.views.billing import billing
from monstagpt.blueprints.billing.views.stripe_webhook import stripe_webhook
from monstagpt.blueprints.stripe_payments.views import stripe_payments
from monstagpt.blueprints.contact.views import contact
from monstagpt.blueprints.gpt.views import gpt
from monstagpt.blueprints.api.views import api
from monstagpt.blueprints.ignite.views import ignite
from monstagpt.blueprints.insights_api.views import insights_api
from monstagpt.blueprints.oai_webhook.views import oai_webhook
from monstagpt.blueprints.data_marketplace.views import data_marketplace
from monstagpt.blueprints.page.views import page
from monstagpt.blueprints.up.views import up
from monstagpt.blueprints.user.models import User
from monstagpt.blueprints.user.views import user
from monstagpt.extensions import babel
from monstagpt.extensions import csrf
from monstagpt.extensions import db
# from monstagpt.extensions import debug_toolbar
from monstagpt.extensions import flask_static_digest
from monstagpt.extensions import login_manager
from monstagpt.extensions import mail


def create_celery_app(app=None):
    """
    Create a new Celery object and tie together the Celery config to the app's
    config. Wrap all tasks in the context of the application.

    :param app: Flask app
    :return: Celery app
    """
    app = app or create_app()

    celery = Celery(app.import_name)
    celery.conf.update(app.config.get("CELERY_CONFIG", {}))

    # Define queues
    
    celery.conf.task_queues = (
        Queue('queue1', Exchange('queue1'), routing_key='queue1'),
        Queue('queue2', Exchange('queue2'), routing_key='queue2'),
    )

    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    return celery


def create_app(settings_override=None):
    """
    Create a Flask application using the app factory pattern.

    :param settings_override: Override settings
    :return: Flask app
    """
    app = Flask(__name__, static_folder="../assets/static", static_url_path="")

    app.config.from_object("config.settings")

    if settings_override:
        app.config.update(settings_override)

    stripe.api_key = app.config.get("STRIPE_SECRET_KEY")
    stripe.api_version = app.config.get("STRIPE_API_VERSION")

    # app.logger.setLevel(app.config['LOG_LEVEL'])

    middleware(app)
    error_templates(app)
    exception_handler(app)
    app.register_blueprint(up)
    app.register_blueprint(admin)
    app.register_blueprint(page)
    app.register_blueprint(contact)
    app.register_blueprint(user)
    app.register_blueprint(billing)
    app.register_blueprint(data_marketplace)
    app.register_blueprint(stripe_webhook)
    app.register_blueprint(gpt)
    app.register_blueprint(api)
    app.register_blueprint(ignite)
    app.register_blueprint(insights_api)
    app.register_blueprint(oai_webhook)
    app.register_blueprint(stripe_payments)
    template_processors(app)
    extensions(app)
    authentication(app, User)
    locale(app)
    register_cli_commands(app)

    return app


def extensions(app):
    """
    Register 0 or more extensions (mutates the app passed in).

    :param app: Flask application instance
    :return: None
    """
    # debug_toolbar.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    babel.init_app(app)
    flask_static_digest.init_app(app)

    return None


def template_processors(app):
    """
    Register 0 or more custom template processors (mutates the app passed in).

    :param app: Flask application instance
    :return: App jinja environment
    """
    app.jinja_env.filters["format_currency"] = format_currency
    app.jinja_env.globals.update(current_year=current_year)
    app.jinja_env.filters['after_underscore'] = split_after_underscore

    return app.jinja_env


def authentication(app, user_model):
    """
    Initialize the Flask-Login extension (mutates the app passed in).

    :param app: Flask application instance
    :param user_model: Model that contains the authentication information
    :type user_model: SQLAlchemy model
    :return: None
    """
    login_manager.login_view = "user.login"

    @login_manager.user_loader
    def load_user(uid):
        user = user_model.query.get(uid)

        if user:
            if not user.is_active():
                login_manager.login_message_category = "error"
                login_manager.login_message = "This account has been disabled."

                return None

            return user
        return None



def locale(app):
    """
    Initialize a locale for the current request.

    :param app: Flask application instance
    :return: str
    """
    if babel.locale_selector_func is None:

        @babel.localeselector
        def get_locale():
            if current_user.is_authenticated:
                return current_user.locale

            accept_languages = app.config.get("LANGUAGES").keys()
            return request.accept_languages.best_match(accept_languages)


def middleware(app):
    """
    Register 0 or more middleware (mutates the app passed in).

    :param app: Flask application instance
    :return: None
    """
    # Enable the Flask interactive debugger in the brower for development.
    if app.debug:
        app.wsgi_app = DebuggedApplication(app.wsgi_app, evalex=True)

    # Set the real IP address into request.remote_addr when behind a proxy.
    app.wsgi_app = ProxyFix(app.wsgi_app)

    return None


def error_templates(app):
    """
    Register 0 or more custom error pages (mutates the app passed in).

    :param app: Flask application instance
    :return: None
    """

    def render_status(status):
        """
        Render a custom template for a specific status.
          Source: http://stackoverflow.com/a/30108946

        :param status: Status as a written name
        :type status: str
        :return: None
        """
        # Get the status code from the status, default to a 500 so that we
        # catch all types of errors and treat them as a 500.
        code = getattr(status, "code", 500)
        return render_template("errors/{0}.html".format(code)), code

    for error in [404, 429, 500]:
        app.errorhandler(error)(render_status)

    return None




def exception_handler(app):
    """
    Register 0 or more exception handlers (mutates the app passed in).

    :param app: Flask application instance
    :return: None
    """
    if not any(isinstance(handler, CustomLoggingHandler) for handler in app.logger.handlers): # This line checks to see if there is already a logger setup
        mail_handler = CustomLoggingHandler()
        mail_handler.setLevel(logging.ERROR)
        mail_handler.setFormatter(logging.Formatter("""
            Time:               %(asctime)s
            Message type:       %(levelname)s

            Message:

            %(message)s
            """))
        app.logger.addHandler(mail_handler)

    return None


celery_app = create_celery_app()
