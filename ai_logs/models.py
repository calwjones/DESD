from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class AIInteraction(models.Model):
    # Track which AI service made the prediction
    SERVICE_TYPES = [
        ('quality', 'Quality Grading'),
        ('demand', 'Demand Forecasting'),
    ]
    
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPES)
    
    # Who triggered this prediction (which user was interacting with the system)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # When did this prediction happen
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # What data was sent to the AI model (stored as JSON)
    # Example: {"product_id": 5, "image_path": "/media/products/tomatoes.jpg"}
    input_data = models.JSONField()
    
    # What did the AI predict (stored as JSON)
    # Example: {"grade": "A", "color": 85, "size": 90, "ripeness": 80}
    prediction = models.JSONField()
    
    # Did the user override/reject the AI's prediction
    user_override = models.BooleanField(default=False)
    
    # If they overrode it, what did they choose instead
    override_value = models.JSONField(null=True, blank=True)
    
    # Which version of the model made this prediction
    # Important for tracking when we retrain models
    model_version = models.CharField(max_length=50)
    
    # How confident was the model (0.0 to 1.0)
    confidence_score = models.FloatField(null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']  # Newest first
        # Add database indexes for faster queries
        indexes = [
            models.Index(fields=['service_type', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['user_override']),
        ]
    
    def __str__(self):
        return f"{self.service_type} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"