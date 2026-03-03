from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProducerProfileForm
from .models import ProducerProfile


@login_required
def edit_profile(request):
    if request.user.role != 'producer':
        return redirect('marketplace')

    profile, _ = ProducerProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = ProducerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('producer_dashboard')
    else:
        form = ProducerProfileForm(instance=profile)

    return render(request, 'producers/profile_edit.html', {'form': form})
