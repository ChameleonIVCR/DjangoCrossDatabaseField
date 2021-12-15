import importlib
import inspect
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.utils.text import capfirst
from django.forms import UUIDField
from django.core import exceptions
from django.db import models
from django import forms

class ReadOnlyCrossDatabaseField(models.Field):
    def __init__(
        self,
        *args,
        **kwargs
    ):
        self.to = args[0] if 0 < len(args) else None
        self.database = args[1] if 1 < len(args) else None
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return self.to_python(value.pk)

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = self.to_python(value)

        if connection.features.has_native_uuid_field:
            return value
        return value.hex

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return self._parse_field(value)

    def to_python(self, value):
        if isinstance(value, uuid.UUID):
            return self._parse_field(value)
        elif inspect.isclass(value) or value is None:
            return value

        return self._parse_field(value)

    def _parse_field(self, remote_id: uuid.UUID):

        callable_path = self.to.rsplit(".", 1)
        module = importlib.import_module(callable_path[0])
        model = getattr(module, callable_path[1])
        return model.objects.using(self.database).get(pk=remote_id)


class CrossField(models.Field):
    def clean(self, value, model_instance):
        """
        Convert the value's type and run validation. Validation errors
        from to_python() and validate() are propagated. Return the correct
        value if no error is raised.
        """
        value = self._return_uuid(value)
        self.validate(value, model_instance)
        self.run_validators(value)
        return value

    def formfield(self, form_class=None, choices_form_class=None, **kwargs):
        """Return a django.forms.Field instance for this field."""
        defaults = {
            'required': not self.blank,
            'label': capfirst(self.verbose_name),
            'help_text': self.help_text,
        }
        if self.has_default():
            if callable(self.default):
                defaults['initial'] = self.default
                defaults['show_hidden_initial'] = True
            else:
                defaults['initial'] = self.get_default()
        if self.choices is not None:
            # Fields with choices get special treatment.
            include_blank = (self.blank or
                             not (self.has_default() or 'initial' in kwargs))
            defaults['choices'] = self.get_choices(include_blank=include_blank)
            defaults['coerce'] = self._return_uuid
            if self.null:
                defaults['empty_value'] = None
            if choices_form_class is not None:
                form_class = choices_form_class
            else:
                form_class = forms.TypedChoiceField
            # Many of the subclass-specific formfield arguments (min_value,
            # max_value) don't apply for choice fields, so be sure to only pass
            # the values that TypedChoiceField will understand.
            for k in list(kwargs):
                if k not in ('coerce', 'empty_value', 'choices', 'required',
                             'widget', 'label', 'initial', 'help_text',
                             'error_messages', 'show_hidden_initial', 'disabled'):
                    del kwargs[k]
        defaults.update(kwargs)
        if form_class is None:
            form_class = forms.CharField
        return form_class(**defaults)

    def _return_uuid(self, value):
        pass


class CrossDatabaseFormField(UUIDField):
    def prepare_value(self, value):
        if isinstance(value, uuid.UUID):
            return str(value)
        return value.pk


class SimpleCrossDatabaseField(CrossField):
    default_error_messages = {
        'invalid': '“%(value)s” is not a valid UUID.',
    }
    description = 'Read-only cross database field'
    empty_strings_allowed = False

    def __init__(self, to: str, remote_db: str, verbose_name=None, **kwargs):
        """
        A read-only cross database field. Currently, only UUID identifiers are supported.

        To get started, declare a Model in another database, with a UUIDField as pk, then pass
        the path as the "to" param, and the database name as "remote_db".

        :param to: Path to model, as a string. Ej: "app.models.MyModel".
        :param remote_db: Database to read the model from, as declared in settings.
        :param verbose_name: Name to represent this field.
        :param kwargs: Django positional arguments.
        """
        kwargs['max_length'] = 32
        self.to = to
        self.remote_db = remote_db
        super().__init__(verbose_name, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs['max_length']
        kwargs['to'] = self.to
        kwargs['remote_db'] = self.remote_db
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        """
        Parses a UUID value, and returns the remote model of it. Used on code occurrences, ej:
        "Model.objects.first().cross_field", where cross_field is this field.
        """
        if value is None:
            return value
        return self._parse_field(value)

    def get_internal_type(self):
        """
        Uses UUIDField logic to store the remote primary key
        """
        return "UUIDField"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return self._return_uuid(value)

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = self._return_uuid(value)

        if connection.features.has_native_uuid_field:
            return value
        return value.hex

    def to_python(self, value):
        """
        Takes any compatible value, parses it to uuid.UUID, and returns it.
        Used in Forms display.
        """
        return self._parse_field(
            self._parse_uuid(value)
        )

    def formfield(self, **kwargs):
        """
        Sets the Form Field to use in the admin to edit the object.
        """
        return super().formfield(**{
            'form_class': CrossDatabaseFormField,
            **kwargs,
        })

    def _return_uuid(self, value):
        """
        Takes any compatible value, parses it to uuid.UUID, and returns it.
        Used in Forms display.
        """
        return self._parse_uuid(value)

    def _parse_field(self, remote_id: uuid.UUID):
        """
        Parses a UUID object, and returns the remote model
        """
        callable_path = self.to.rsplit(".", 1)
        module = importlib.import_module(callable_path[0])
        model = getattr(module, callable_path[1])
        try:
            return model.objects.using(self.remote_db).get(pk=remote_id)
        except ObjectDoesNotExist:
            return None

    def _parse_uuid(self, value):
        """
        Parses a compatible object, and returns an uuid.UUID object
        """
        if value is not None and not isinstance(value, uuid.UUID):
            input_form = 'int' if isinstance(value, int) else 'hex'
            try:
                value = uuid.UUID(**{input_form: value})
            except (AttributeError, ValueError):
                raise exceptions.ValidationError(
                    self.error_messages['invalid'],
                    code='invalid',
                    params={'value': value},
                )
        return value


class Libro(models.Model):
    nombre = models.CharField()


class UserLocalProxy(models.Model):
    user_proxy = SimpleCrossDatabaseField(
        to="users.models.UserProxy",
        remote_db="users"
    )
    libros = models.ManyToManyField(Libro)


# region Users database
class UserProxy(models.Model):
    # Primary key for foreign relationships
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE
    )

    class Meta:
        app_label = "auth"
# endregion
