from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProducerProfileForm
from .models import ProducerProfile
from services.os_places_service import PostcodesService


@login_required
def edit_profile(request):
    if request.user.role != 'producer':
        return redirect('marketplace')

    profile, _ = ProducerProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = ProducerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            updated_profile = form.save(commit=False)
            if updated_profile.postcode:
                location = PostcodesService().lookup_postcode(updated_profile.postcode)
                if location:
                    updated_profile.latitude = location['latitude']
                    updated_profile.longitude = location['longitude']
            updated_profile.save()
            messages.success(request, 'Profile updated.')
            return redirect('producer_dashboard')
    else:
        form = ProducerProfileForm(instance=profile)

    return render(request, 'producers/profile_edit.html', {'form': form})
