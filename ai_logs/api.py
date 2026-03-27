from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import AIInteraction
from .serializers import AIInteractionSerializer

class AIInteractionViewSet(viewsets.ModelViewSet):
    # ModelViewSet = allows GET, POST, PUT, DELETE
    # AI services can POST logs, admins can GET logs for analysis
    
    queryset = AIInteraction.objects.all()
    serializer_class = AIInteractionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Start with all logs
        queryset = super().get_queryset()
        
        # Optional filtering by service type
        # Example: /api/ai-logs/?service_type=quality
        service_type = self.request.query_params.get('service_type')
        if service_type:
            queryset = queryset.filter(service_type=service_type)
        
        # Optional filtering by date range
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        # Optional filtering for overrides only
        # Example: /api/ai-logs/?user_override=true
        # This finds cases where users rejected AI predictions
        user_override = self.request.query_params.get('user_override')
        if user_override == 'true':
            queryset = queryset.filter(user_override=True)
        
        return queryset