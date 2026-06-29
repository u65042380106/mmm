# myproject/urls.py
from django.contrib import admin
from django.urls import path, include
from myapp import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index_view, name='index'), 
    path('accounts/', include('allauth.urls')),
    path('profile/', views.profile_view, name='profile'),
    path('search/', views.search_view, name='search'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('manage-members/', views.manage_members_view, name='manage_members'),
    path('delete-member/<int:user_id>/', views.delete_member_view, name='delete_member'),
    path('history/', views.history_view, name='history'),
    path('history/<int:history_id>/', views.result_detail_view, name='result_detail'),
    path('history/delete/<int:history_id>/', views.delete_history_view, name='delete_history'),
    path('compare/', views.compare_view, name='compare'),
]