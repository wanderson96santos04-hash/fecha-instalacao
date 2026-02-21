from flask import Blueprint, render_template

bp = Blueprint(
    "acquisition",
    __name__,
    url_prefix="/acquisition",
    template_folder="templates",
)

@bp.get("/")
def acquisition_home():
    return render_template("acquisition/acquisition.html")
