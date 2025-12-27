"""
Custom field for generating short, unique identifiers in Django models.

This module provides a custom field type that automatically generates
5-character unique identifiers using uppercase letters and numbers.
Ideal for creating human-readable, short IDs for database records.

Example:
    class Patient(models.Model):
        patient_id = ShortUUIDField(primary_key=True)
        # Will generate IDs like: 'A12B4', 'X9Y3Z', etc.

Author: Robert
Date: October 28, 2025
"""

from django.db import models
import random
import string

class ShortUUIDField(models.CharField):
    """
    A custom field that generates 5-character unique identifiers.
    
    This field automatically generates unique IDs using a combination of
    uppercase letters (A-Z) and numbers (0-9). It ensures uniqueness
    within the model and is not editable after creation.
    
    Attributes:
        max_length (int): Fixed at 5 characters
        unique (bool): Always True to ensure uniqueness
        editable (bool): False to prevent manual editing
    
    Note:
        - IDs are generated only when creating new records
        - Existing records maintain their IDs
        - Format example: 'A12B4', 'X9Y3Z'
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the field with fixed settings for consistent ID generation.
        
        Args:
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments
        
        Note:
            Overrides any user-provided max_length, unique, and editable settings
            to ensure consistent behavior.
        """
        kwargs['max_length'] = 5  # Fixed length for all IDs
        kwargs['unique'] = True   # Ensure uniqueness
        kwargs['editable'] = False  # Prevent manual editing
        super().__init__(*args, **kwargs)

    def generate_id(self):
        """
        Generate a random 5-character string using uppercase letters and numbers.
        
        Returns:
            str: A 5-character string containing uppercase letters and numbers
            
        Example:
            'A12B4', 'X9Y3Z', '12ABC'
        """
        chars = string.ascii_uppercase + string.digits  # A-Z and 0-9
        return ''.join(random.choices(chars, k=5))

    def pre_save(self, model_instance, add):
        """
        Generate and set a unique ID before saving if this is a new record.
        
        Args:
            model_instance: The model instance being saved
            add (bool): Whether this is a new record
            
        Returns:
            str: The final value to be saved
            
        Note:
            Will keep generating new IDs until a unique one is found
        """
        if add and not getattr(model_instance, self.attname):
            value = self.generate_id()
            # Keep generating until we find a unique value
            while model_instance.__class__.objects.filter(**{self.attname: value}).exists():
                value = self.generate_id()
            setattr(model_instance, self.attname, value)
        return super().pre_save(model_instance, add)