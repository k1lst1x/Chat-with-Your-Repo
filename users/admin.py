from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from users.forms import UserCreationForm

User = get_user_model()


# @admin.register(User)
# class UserAdmin(UserAdmin):
#     add_fieldsets = (
#         (None, {
#             'classes': ('wide',),
#             'fields': ('username', 'email', 'password1', 'password2'),
#         }),
#     )

#     add_form = UserCreationForm

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'is_subscribed'),
        }),
    )

    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Subscription', {'fields': ('is_subscribed',)}),
    )

    list_display = ('email', 'username', 'first_name', 'last_name', 'is_staff', 'is_subscribed')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('email',)