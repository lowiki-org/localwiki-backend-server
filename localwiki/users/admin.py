from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import ugettext_lazy as _
from users.models import UserProfile
from django.views.generic.list import ListView


class CensoredUserAdmin(UserAdmin):
    "UserAdmin that does not show a user's email address or password hash"

    list_display = ('username', 'first_name', 'last_name', 'is_staff')
    search_fields = ('username', 'first_name', 'last_name')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2')}
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:
            return self.readonly_fields + ('is_staff', 'is_superuser',)
        return self.readonly_fields


admin.site.unregister(User)
admin.site.register(User, CensoredUserAdmin)


class SubscribedList(ListView):
    queryset = UserProfile.objects.filter(subscribed=True, user__is_active=True)
    template_name = 'users/subscribed_list.html'
