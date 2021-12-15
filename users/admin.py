from django.contrib import admin
from .models import UserLocalProxy, UserProxy

# Register your models here.
admin.site.register(UserLocalProxy)
admin.site.register(UserProxy)
