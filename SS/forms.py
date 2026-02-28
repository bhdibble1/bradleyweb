from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, TextAreaField, BooleanField, PasswordField, FileField
from flask_wtf.file import FileAllowed
from wtforms.validators import NumberRange
from wtforms.validators import DataRequired, Length, Email, EqualTo

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class PremiumCSRFForm(FlaskForm):
    """Minimal form for CSRF token on premium page forms."""
    pass


class QuitNicotineGuideForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Get the free guide')

class ProductForm(FlaskForm):
    product_name = StringField(
        'Product Name',
        validators=[DataRequired(), Length(max=100)]
    )

    product_description = TextAreaField(
        'Product Description',
        validators=[DataRequired(), Length(max=500)]
    )

    quantity = IntegerField(
        'Quantity',
        validators=[DataRequired(), NumberRange(min=1, message='Quantity must be at least 1')]
    )

    product_image = FileField(
        'Product Image',
        validators=[FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')]
    )

    featured = BooleanField('Featured')

    submit = SubmitField('Submit')