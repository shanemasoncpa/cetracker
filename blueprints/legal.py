from flask import Blueprint, render_template

legal_bp = Blueprint('legal', __name__)


@legal_bp.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')
