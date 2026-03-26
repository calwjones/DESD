import math
import requests


class PostcodesService:
    """
    Service class for interacting with the postcodes.io API.
    Handles postcode lookup and food miles calculation.
    No API key required — completely free.
    API docs: https://postcodes.io
    """

    BASE_URL = "https://api.postcodes.io/postcodes"

    # Sentinel returned when the API cannot be reached (network/timeout)
    NETWORK_ERROR = "POSTCODE_NETWORK_ERROR"

    @staticmethod
    def _normalise(postcode):
        clean = postcode.strip().upper().replace(" ", "")
        # Re-insert space before the last 3 chars (inward code is always 3 chars)
        # e.g. BS160HT → BS16 0HT, TA27DW → TA2 7DW
        if len(clean) >= 5:
            return f"{clean[:-3]} {clean[-3:]}"
        return clean

    def lookup_postcode(self, postcode):
        """
        Look up a postcode and return address details with lat/lng.
        Returns:
          dict          — success
          None          — postcode not found / invalid (HTTP 404)
          NETWORK_ERROR — could not reach the API (connection/timeout)
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/{self._normalise(postcode)}",
                timeout=5,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return self.NETWORK_ERROR

        if response.status_code == 404:
            return None

        try:
            response.raise_for_status()
            result = response.json().get('result', {})
            if not result:
                return None
            return {
                'address': f"{result.get('admin_ward', '')}, {result.get('admin_district', '')}",
                'town': result.get('admin_district', ''),
                'postcode': result.get('postcode', ''),
                'latitude': result.get('latitude'),
                'longitude': result.get('longitude'),
            }
        except requests.RequestException:
            return self.NETWORK_ERROR

    def is_valid(self, postcode):
        """
        Check whether a postcode is valid.
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/{self._normalise(postcode)}/validate",
                timeout=5,
            )
            return response.json().get('result', False)
        except requests.RequestException:
            return False

    @staticmethod
    def calculate_food_miles(lat1, lon1, lat2, lon2):
        """
        Calculate straight-line distance in miles between two lat/lng points
        using the Haversine formula.
        """
        R = 3958.8  # Earth radius in miles
        lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return round(R * 2 * math.asin(math.sqrt(a)), 1)
