from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from products.ai_grading import grade_product_image
from .forms import ProductForm
from .models import Product
from services.os_places_service import PostcodesService


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    food_miles = PostcodesService.get_food_miles(request.user, product.producer)
    return render(request, 'products/product_detail.html', {
        'product': product,
        'food_miles': food_miles,
        'customer_has_postcode': bool(request.user.postcode),
    })


@login_required
def product_add(request):
    if request.user.role != 'producer':
        return redirect('marketplace')
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.producer = request.user
            product.save()

            # Call AI grading service (fails gracefully). Producer can opt out.
            grading_enabled = form.cleaned_data.get('enable_ai_grading', True)
            if grading_enabled and product.image and product.category in ('fruit', 'vegetables'):
                graded = grade_product_image(product)
                if graded:
                    messages.success(request, 'Product added and quality assessed.')
                else:
                    messages.success(request, 'Product added. Quality assessment pending.')
            else:
                messages.success(request, 'Product added successfully.')

            return redirect('producer_dashboard')
    else:
        form = ProductForm()
    return render(request, 'products/product_form.html', {'form': form, 'action': 'Add'})



@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, producer=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            old_image = product.image.name if product.image else None
            product = form.save()

            # Re-grade if image changed and producer didn't opt out
            grading_enabled = form.cleaned_data.get('enable_ai_grading', True)
            if grading_enabled and 'image' in request.FILES and product.category in ('fruit', 'vegetables'):
                graded = grade_product_image(product)
                if graded:
                    messages.success(request, 'Product updated and quality re-assessed.')
                else:
                    messages.success(request, 'Product updated. Quality re-assessment pending.')
            else:
                messages.success(request, 'Product updated.')

            return redirect('producer_dashboard')
    else:
        form = ProductForm(instance=product)
    return render(request, 'products/product_form.html', {'form': form, 'action': 'Edit'})


@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, producer=request.user)
    if request.method == 'POST':
        product.delete()
        messages.success(request, 'Product deleted.')
        return redirect('producer_dashboard')
    return render(request, 'products/product_confirm_delete.html', {'product': product})


@login_required
def challenge_grade(request, pk):
    product = get_object_or_404(Product, pk=pk, producer=request.user)
    if request.method == 'POST':
        suggested_grade = request.POST.get('suggested_grade')
        if suggested_grade in ('A', 'B', 'C'):
            # Find the latest AI interaction for this product
            from ai_logs.models import AIInteraction
            interaction = AIInteraction.objects.filter(
                input_data__product_id=product.pk,
                service_type='quality',
            ).order_by('-timestamp').first()

            if interaction:
                interaction.user_override = True
                interaction.override_value = {
                    'suggested_grade': suggested_grade,
                    'original_grade': product.quality_grade,
                    'reason': request.POST.get('reason', ''),
                }
                interaction.save()

            messages.success(request, f'Grade challenge submitted. You suggested Grade {suggested_grade}.')
        else:
            messages.error(request, 'Invalid grade selected.')
    return redirect('products:detail', pk=pk)