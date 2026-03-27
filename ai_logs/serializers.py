from rest_framework import serializers
from .models import AIInteraction

class AIInteractionSerializer(serializers.ModelSerializer):
    # Simple serializer - just expose all fields as-is
    # No flattening needed here
    
    class Meta:
        model = AIInteraction
        fields = '__all__'  # Include all fields from the model
        read_only_fields = ['timestamp']  # Timestamp is auto-generated, can't be set manually