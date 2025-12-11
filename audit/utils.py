# audit/utils.py

import requests
import time
from functools import lru_cache
from django.core.cache import cache


def get_client_ip(request):
    """
    Extract real client IP address from request.
    Handles proxies, load balancers, and CDNs.
    """
    # Check X-Forwarded-For header (used by proxies/load balancers)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP (client's real IP)
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        # Fallback to REMOTE_ADDR
        ip = request.META.get('REMOTE_ADDR')
    
    # Handle localhost for development
    if ip in ['127.0.0.1', 'localhost', '::1']:
        return '127.0.0.1'
    
    return ip


@lru_cache(maxsize=1000)
def geolocate_ip(ip_address):
    """
    Get geolocation data for an IP address.
    Uses ip-api.com (free tier: 45 requests/minute).
    Caches results to avoid hitting rate limits.
    
    Returns dict with: country, region, city, lat, lon
    """
    # Skip localhost
    if ip_address in ['127.0.0.1', 'localhost', '::1']:
        return {
            'country': 'Local',
            'region': 'Development',
            'city': 'Localhost',
            'latitude': None,
            'longitude': None,
            'timezone': 'UTC'
        }
    
    # Check cache first (24 hour TTL)
    cache_key = f"geoip:{ip_address}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    try:
        # Use ip-api.com (free, no key required)
        response = requests.get(
            f"http://ip-api.com/json/{ip_address}",
            timeout=2
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'success':
                geo_data = {
                    'country': data.get('country', ''),
                    'region': data.get('regionName', ''),
                    'city': data.get('city', ''),
                    'latitude': data.get('lat'),
                    'longitude': data.get('lon'),
                    'timezone': data.get('timezone', ''),
                    'isp': data.get('isp', ''),
                }
                
                # Cache for 24 hours
                cache.set(cache_key, geo_data, 86400)
                return geo_data
        
        # Rate limit handling
        if response.status_code == 429:
            print(f"IP geolocation rate limited for {ip_address}")
            time.sleep(1)
            
    except Exception as e:
        print(f"Geolocation error for {ip_address}: {e}")
    
    # Return empty data on failure
    return {
        'country': '',
        'region': '',
        'city': '',
        'latitude': None,
        'longitude': None,
        'timezone': ''
    }


def calculate_risk_score(user, ip_address, action, geo_data):
    """
    Calculate risk score for an audit log entry.
    Returns 0-100 (higher = more suspicious)
    """
    risk = 0
    
    # Check for unusual access patterns
    # 1. PHI access outside business hours
    from datetime import datetime
    hour = datetime.now().hour
    if action in ['PHI_READ', 'TOOL_CALL'] and (hour < 6 or hour > 22):
        risk += 15
    
    # 2. Access from new country
    if geo_data.get('country'):
        from audit.models import AuditLog
        prev_countries = set(
            AuditLog.objects
            .filter(user=user)
            .exclude(country='')
            .values_list('country', flat=True)
            .distinct()[:10]
        )
        
        if prev_countries and geo_data['country'] not in prev_countries:
            risk += 25
    
    # 3. Multiple failed access attempts
    if action == 'ACCESS_DENIED':
        from audit.models import AuditLog
        recent_denials = AuditLog.objects.filter(
            user=user,
            action='ACCESS_DENIED',
            timestamp__gte=datetime.now() - timedelta(hours=1)
        ).count()
        
        if recent_denials > 3:
            risk += 30
    
    # 4. Access to sensitive tools
    sensitive_tools = ['get_patient_phi', 'get_medical_records']
    if action == 'TOOL_CALL' and any(tool in str(geo_data) for tool in sensitive_tools):
        risk += 10
    
    return min(risk, 100)  # Cap at 100


def log_tool_call(user, tool_name, arguments, result, duration_ms, request, access_granted=True, denial_reason=''):
    """
    Comprehensive logging for all tool calls.
    """
    from audit.models import AuditLog
    from datetime import timedelta
    
    # Get IP and geolocation
    ip_address = get_client_ip(request)
    geo_data = geolocate_ip(ip_address)
    
    # Determine if PHI access
    phi_tools = ['get_patient_phi', 'get_medical_records']
    is_phi = tool_name in phi_tools
    
    # Calculate risk score
    risk_score = calculate_risk_score(user, ip_address, 'TOOL_CALL', geo_data)
    
    # Determine action type
    if access_granted:
        action = 'PHI_READ' if is_phi else 'TOOL_SUCCESS'
    else:
        action = 'PHI_DENIED' if is_phi else 'ACCESS_DENIED'
    
    # Create audit log
    AuditLog.objects.create(
        user=user,
        action=action,
        tool_name=tool_name,
        tool_parameters=arguments,
        tool_result_summary=str(result)[:500] if result else '',  # Truncate
        table_name=tool_name.replace('get_', '').replace('_', ''),
        access_granted=access_granted,
        denial_reason=denial_reason,
        duration_ms=duration_ms,
        ip_address=ip_address,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        country=geo_data.get('country', ''),
        region=geo_data.get('region', ''),
        city=geo_data.get('city', ''),
        latitude=geo_data.get('latitude'),
        longitude=geo_data.get('longitude'),
        is_phi_access=is_phi,
        is_suspicious=(risk_score > 50),
        risk_score=risk_score
    )