from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import RegisterForm, CustomerProfileForm
from .models import CustomUser, FavouriteProducer
from services.os_places_service import PostcodesService

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            if user.role == 'producer':
                return redirect('producer_dashboard')
            else:
                return redirect('marketplace')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.role == 'producer':
                return redirect('producer_dashboard')
            else:
                return redirect('marketplace')
        else:
            messages.error(request, 'Invalid username or password')
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('accounts:login')


@login_required
def profile_view(request):
    if request.user.role != 'customer':
        return redirect('producer_dashboard')

    if request.method == 'POST':
        form = CustomerProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            postcode = form.cleaned_data.get('postcode', '').strip()
            if postcode:
                service = PostcodesService()
                location = service.lookup_postcode(postcode)
                if location == PostcodesService.NETWORK_ERROR:
                    form.add_error('postcode', 'Could not reach the postcode service — please try again later.')
                    return render(request, 'accounts/profile.html', {'form': form})
                elif not location:
                    form.add_error('postcode', 'Invalid postcode — please check and try again.')
                    return render(request, 'accounts/profile.html', {'form': form})
                else:
                    request.user.latitude = location['latitude']
                    request.user.longitude = location['longitude']
                    request.user.postcode = location['postcode']
            else:
                request.user.postcode = ''
                request.user.latitude = None
                request.user.longitude = None
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('marketplace')
    else:
        form = CustomerProfileForm(instance=request.user)

    favourites = FavouriteProducer.objects.filter(
        customer=request.user
    ).select_related('producer__producer_profile').order_by('producer__producer_profile__business_name')

    return render(request, 'accounts/profile.html', {'form': form, 'favourites': favourites})


@login_required
def toggle_favourite(request, producer_id):
    if request.method != 'POST' or request.user.role != 'customer':
        return redirect('marketplace')
    producer = get_object_or_404(CustomUser, pk=producer_id, role='producer')
    fav, created = FavouriteProducer.objects.get_or_create(customer=request.user, producer=producer)
    if not created:
        fav.delete()
    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('marketplace')