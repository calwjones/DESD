from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from .forms import RegisterForm, CustomerProfileForm
from services.os_places_service import PostcodesService

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            if user.role == 'logistics':
                return redirect('delivery:logistics_dashboard')
            elif user.role == 'producer':
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
            if user.role == 'logistics':
                return redirect('delivery:logistics_dashboard')
            elif user.role == 'producer':
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

    return render(request, 'accounts/profile.html', {'form': form})