from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProductForm
from .models import Product


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return render(request, 'products/product_detail.html', {'product': product})


@login_required
def product_add(request):
    if request.user.role != 'producer':
        return redirect('marketplace')
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.producer = request.user
            product.save()
            messages.success(request, 'Product added successfully.')
            return redirect('producer_dashboard')
    else:
        form = ProductForm()
    return render(request, 'products/product_form.html', {'form': form, 'action': 'Add'})


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, producer=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
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
