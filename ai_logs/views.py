from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from ai_logs.models import AIInteraction
from products.models import Product


@api_view(['POST'])
@permission_classes([IsAdminUser])
def resolve_challenge(request, pk):
    try:
        interaction = AIInteraction.objects.get(pk=pk, user_override=True)
    except AIInteraction.DoesNotExist:
        return Response({'error': 'Challenge not found'}, status=404)

    action = request.data.get('action')  # 'approve' or 'reject'

    if action == 'approve':
        # Update the product's grade to the suggested one
        product_id = interaction.input_data.get('product_id')
        suggested = interaction.override_value.get('suggested_grade')
        if product_id and suggested:
            Product.objects.filter(pk=product_id).update(quality_grade=suggested)
        interaction.override_value['resolved'] = 'approved'
        interaction.save()
        return Response({'status': 'approved', 'new_grade': suggested})

    elif action == 'reject':
        interaction.override_value['resolved'] = 'rejected'
        interaction.save()
        return Response({'status': 'rejected'})

    return Response({'error': 'Invalid action'}, status=400)