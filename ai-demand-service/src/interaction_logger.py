import os
import requests

DESD_API_URL = os.environ.get("DESD_API_URL", "http://localhost:8089/api")
DESD_USERNAME = os.environ.get("DESD_SERVICE_USERNAME", "admin")
DESD_PASSWORD = os.environ.get("DESD_SERVICE_PASSWORD", "demo1234")


class InteractionLogger:
    def __init__(self):
        self._session = None

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session

        session = requests.Session()
        login_url = f"{DESD_API_URL.rsplit('/api', 1)[0]}/accounts/login/"
        try:
            session.get(login_url, timeout=5)
            csrftoken = session.cookies.get("csrftoken", "")

            login_resp = session.post(
                login_url,
                data={
                    "username": DESD_USERNAME,
                    "password": DESD_PASSWORD,
                    "csrfmiddlewaretoken": csrftoken,
                },
                headers={"Referer": login_url},
                timeout=5,
                allow_redirects=False,
            )
            if login_resp.status_code in (200, 302):
                self._session = session
                return session
        except requests.RequestException as e:
            print(f"Could not connect to DESD: {e}")

        return session

    def log(self, service_type, user_id, input_data, prediction, model_version, confidence_score=None, user_override=False):
        """Log a prediction to DESD. Returns the created log's id, or None on failure."""
        payload = {
            "service_type": service_type,
            "user": user_id,
            "input_data": input_data,
            "prediction": prediction,
            "model_version": model_version,
            "confidence_score": confidence_score,
            "user_override": user_override,
        }

        try:
            session = self._get_session()
            csrftoken = session.cookies.get("csrftoken", "")
            resp = session.post(
                f"{DESD_API_URL}/ai-logs/",
                json=payload,
                headers={"X-CSRFToken": csrftoken, "Referer": DESD_API_URL},
                timeout=5,
            )
            if resp.status_code == 201:
                try:
                    return resp.json().get("id")
                except ValueError:
                    return None
            print(f"Log POST failed: {resp.status_code} {resp.text[:200]}")
            return None
        except requests.RequestException as e:
            print(f"Could not log to DESD: {e}")
            return None

    def fetch_logs(self, service_type=None, start_date=None, end_date=None, overrides_only=False) -> list:
        params = {}
        if service_type:
            params["service_type"] = service_type
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if overrides_only:
            params["user_override"] = "true"

        try:
            session = self._get_session()
            resp = session.get(f"{DESD_API_URL}/ai-logs/", params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("results", resp.json())
            print(f"Log fetch failed: {resp.status_code}")
            return []
        except requests.RequestException as e:
            print(f"Could not fetch logs from DESD: {e}")
            return []
