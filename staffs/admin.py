from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(User)
admin.site.register(Document)
admin.site.register(Organization)
admin.site.register(Chat)
admin.site.register(ChatMessage)
