import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from orders.models import Settlement
from products.models import Product
from services.os_places_service import PostcodesService

from .forms import ProducerProfileForm
from .models import ProducerProfile, Recipe, FarmStory


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
                if location == PostcodesService.NETWORK_ERROR:
                    form.add_error('postcode', 'Could not reach the postcode service — please try again later.')
                    return render(request, 'producers/profile_edit.html', {'form': form})
                elif not location:
                    form.add_error('postcode', 'Invalid postcode — please check and try again.')
                    return render(request, 'producers/profile_edit.html', {'form': form})
                else:
                    updated_profile.latitude = location['latitude']
                    updated_profile.longitude = location['longitude']
            updated_profile.save()
            messages.success(request, 'Profile updated.')
            return redirect('producer_dashboard')
    else:
        form = ProducerProfileForm(instance=profile)

    return render(request, 'producers/profile_edit.html', {'form': form})


def _producer_only(request):
    """Return None if the user is a producer, else a redirect."""
    if request.user.role != 'producer':
        return redirect('marketplace')
    return None


@login_required
def settlements_list(request):
    """BRFN-44: Producer's weekly payment history with running YTD total."""
    redirect_response = _producer_only(request)
    if redirect_response:
        return redirect_response

    settlements = Settlement.objects.filter(producer=request.user)

    today = date.today()
    ytd = (
        Settlement.objects
        .filter(producer=request.user, period_end__year=today.year)
        .aggregate(
            gross=Sum('gross_amount'),
            commission=Sum('commission_amount'),
            net=Sum('net_amount'),
        )
    )
    ytd_totals = {
        'year': today.year,
        'gross': ytd['gross'] or Decimal('0'),
        'commission': ytd['commission'] or Decimal('0'),
        'net': ytd['net'] or Decimal('0'),
    }

    return render(request, 'producers/settlements_list.html', {
        'settlements': settlements,
        'ytd': ytd_totals,
    })


@login_required
def settlement_detail(request, settlement_id):
    """Show contributing orders for a single settlement."""
    redirect_response = _producer_only(request)
    if redirect_response:
        return redirect_response

    settlement = get_object_or_404(
        Settlement, id=settlement_id, producer=request.user
    )
    splits = (
        settlement.splits
        .select_related('payment__order__customer', 'payment')
        .order_by('payment__created_at')
    )

    return render(request, 'producers/settlement_detail.html', {
        'settlement': settlement,
        'splits': splits,
    })


@login_required
def settlement_csv(request, settlement_id):
    """Download a CSV breakdown of a settlement for tax records (TC-012)."""
    redirect_response = _producer_only(request)
    if redirect_response:
        return redirect_response

    settlement = get_object_or_404(
        Settlement, id=settlement_id, producer=request.user
    )

    response = HttpResponse(content_type='text/csv')
    filename = f"settlement_{settlement.period_start}_{settlement.period_end}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Order #', 'Order Date', 'Customer', 'Gross (£)', 'Commission (£)', 'Net (£)',
    ])
    splits = settlement.splits.select_related('payment__order__customer', 'payment')
    for split in splits:
        order = split.payment.order
        writer.writerow([
            order.id,
            split.payment.created_at.date().isoformat(),
            order.customer.username,
            f"{split.gross_amount:.2f}",
            f"{split.commission_amount:.2f}",
            f"{split.net_amount:.2f}",
        ])
    writer.writerow([])
    writer.writerow([
        'TOTAL', '', '',
        f"{settlement.gross_amount:.2f}",
        f"{settlement.commission_amount:.2f}",
        f"{settlement.net_amount:.2f}",
    ])

    return response


@login_required
def recipe_list(request):
    if request.user.role != 'producer':
        return redirect('marketplace')
    return redirect('producers:producer_public_profile', pk=request.user.pk)


@login_required
def recipe_add(request):
    if request.user.role != 'producer':
        return redirect('marketplace')
    if request.method == 'POST':
        recipe = Recipe(
            producer=request.user,
            title=request.POST['title'],
            description=request.POST['description'],
            ingredients=request.POST['ingredients'],
            method=request.POST['method'],
            seasonal_tag=request.POST.get('seasonal_tag', 'year_round'),
        )
        product_id = request.POST.get('product')
        if product_id:
            recipe.product_id = product_id
        if request.FILES.get('image'):
            recipe.image = request.FILES['image']
        recipe.save()
        return redirect('producers:recipe_list')
    products = Product.objects.filter(producer=request.user)
    return render(request, 'producers/recipe_form.html', {'products': products})


@login_required
def recipe_edit(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk, producer=request.user)
    if request.method == 'POST':
        recipe.title = request.POST['title']
        recipe.description = request.POST['description']
        recipe.ingredients = request.POST['ingredients']
        recipe.method = request.POST['method']
        recipe.seasonal_tag = request.POST.get('seasonal_tag', 'year_round')
        product_id = request.POST.get('product')
        recipe.product_id = product_id if product_id else None
        if request.FILES.get('image'):
            recipe.image = request.FILES['image']
        recipe.save()
        return redirect('producers:recipe_list')
    products = Product.objects.filter(producer=request.user)
    return render(request, 'producers/recipe_form.html', {'recipe': recipe, 'products': products})


@login_required
def recipe_delete(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk, producer=request.user)
    if request.method == 'POST':
        recipe.delete()
    return redirect('producers:recipe_list')


def recipe_public_list(request):
    recipes = Recipe.objects.all().select_related('producer__producer_profile').order_by('-created_at')
    return render(request, 'producers/recipe_public_list.html', {'recipes': recipes})

def recipe_detail(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    return render(request, 'producers/recipe_detail.html', {'recipe': recipe})


def producer_public_profile(request, pk):
    User = get_user_model()
    producer = get_object_or_404(User, pk=pk, role='producer')
    profile = get_object_or_404(ProducerProfile, user=producer)
    products = Product.objects.filter(producer=producer, is_available=True)
    recipes = Recipe.objects.filter(producer=producer).order_by('-created_at')
    stories = FarmStory.objects.filter(producer=producer).order_by('-created_at')
    is_favourite = False
    if request.user.is_authenticated and request.user.is_buyer:
        from accounts.models import FavouriteProducer
        is_favourite = FavouriteProducer.objects.filter(
            customer=request.user, producer=producer
        ).exists()
    is_owner = request.user.is_authenticated and request.user == producer
    return render(request, 'producers/producer_public_profile.html', {
        'producer': producer,
        'profile': profile,
        'products': products,
        'recipes': recipes,
        'stories': stories,
        'is_favourite': is_favourite,
        'is_owner': is_owner,
    })

@login_required
def story_list(request):
    if request.user.role != 'producer':
        return redirect('marketplace')
    return redirect('producers:producer_public_profile', pk=request.user.pk)


@login_required
def story_add(request):
    if request.user.role != 'producer':
        return redirect('marketplace')
    if request.method == 'POST':
        story = FarmStory(
            producer=request.user,
            title=request.POST['title'],
            body=request.POST['body'],
        )
        if request.FILES.get('image'):
            story.image = request.FILES['image']
        story.save()
        return redirect('producers:story_list')
    return render(request, 'producers/story_form.html')


@login_required
def story_edit(request, pk):
    story = get_object_or_404(FarmStory, pk=pk, producer=request.user)
    if request.method == 'POST':
        story.title = request.POST['title']
        story.body = request.POST['body']
        if request.FILES.get('image'):
            story.image = request.FILES['image']
        story.save()
        return redirect('producers:story_list')
    return render(request, 'producers/story_form.html', {'story': story})


@login_required
def story_delete(request, pk):
    story = get_object_or_404(FarmStory, pk=pk, producer=request.user)
    if request.method == 'POST':
        story.delete()
    return redirect('producers:story_list')