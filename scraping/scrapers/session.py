#Encargado de manejar la sesión y autenticación.
import requests
import re
from gatfh import config

class MoodleSession:
    def __init__(self, cookie=None):
        """cookie: valor de la cookie MoodleSession del usuario que dispara la operacion.
        Nunca se persiste (ni en DB, ni en archivo, ni en variable global) - solo vive en
        memoria durante esta instancia, que a su vez vive solo durante el request/job que
        la crea (ver README, decision D1b). Cada instancia tiene su propio dict `cookies`,
        asi que dos MoodleSession de dos usuarios distintos nunca se pisan entre si.

        Si no se pasa `cookie`, cae al valor de MOODLE_SESSION_COOKIE del .env (solo como
        comodidad para scripts/CLI locales de un solo usuario) - las vistas web SIEMPRE
        deben pasar el cookie explicito del usuario logueado, nunca depender de este
        fallback."""
        self.base_url = config.BASE_URL
        cookie = cookie or config.COOKIES.get("MoodleSession", "")
        self.cookies = {"MoodleSession": cookie}
        self.sesskey = None
        self.session = requests.Session()
        self.session.cookies.update(self.cookies)

    def get(self,**kwargs):
        # ------------------------------
        # Paso 1: obtener sesskey
        # ------------------------------
        self.session.cookies.update(self.cookies)
        URL=f"{self.base_url}"
        resp = self.session.get(URL)
        html_text = resp.text

        if "/login/" in str(resp.url):
            raise Exception("La sesión de Moodle expiró (la cookie ya no es válida).")

        # Buscar sesskey dentro de M.cfg
        match = re.search(r'"sesskey":"([a-zA-Z0-9]+)"', html_text)
        if not match:
            raise Exception("No se pudo extraer el sesskey. Revisa tu cookie de sesión.")

        sesskey = match.group(1)
        # Se guarda solo en esta instancia (self.sesskey), nunca en un archivo/variable
        # global compartida entre requests de distintos usuarios (antes: config.SESSKEY y
        # config_runtime.json - ver README, hallazgos C1 y "config.SESSKEY mutable").
        self.sesskey = sesskey
        print("Sesskey obtenido:", sesskey)
        return sesskey

    def get_sesskey(self):
        if self.sesskey:
            return self.sesskey
        return self.get()

    def sesskey_valido(self, sesskey):
        try:
            url = f"{self.base_url}/lib/ajax/service.php?sesskey={sesskey}&info=core_webservice_get_site_info"

            resp = self.session.post(url, json=[{
                "index": 0,
                "methodname": "core_webservice_get_site_info",
                "args": {}
            }])

            result = resp.json()

            if isinstance(result, list) and result[0].get("error"):
                errorcode = result[0]["exception"].get("errorcode")
                return errorcode != "invalidsesskey"

            return True

        except Exception:
            return False

    def get_courses(self, endpoint):

        cookies=self.cookies['MoodleSession']
        print("Cookies: ",cookies)
        sesskey = self.get_sesskey()
        print("sesskey: ",sesskey)
        COURSES_URL=f"{self.base_url}{endpoint}"
        print("COURSES_URL: ",COURSES_URL)

        ajax_url = f"{self.base_url}/lib/ajax/service.php?sesskey={sesskey}&info=core_course_get_enrolled_courses_by_timeline_classification"

        data_raw = '[{"index":0,"methodname":"core_course_get_enrolled_courses_by_timeline_classification","args":{"offset":0,"limit":0,"classification":"all","sort":"fullname","customfieldname":"","customfieldvalue":""}}]'

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.base_url,
            "Connection": "keep-alive",
            "Referer": COURSES_URL,
            "Cookie": f"MoodleSession={cookies}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TE": "trailers"
        }

        resp2 = self.session.post(ajax_url, headers=headers, data=data_raw)
        data = resp2.json() 

        return data
        #return self.session.get(f"{self.base_url}{endpoint}", **kwargs)

    def post(self, endpoint, **kwargs):
        return self.session.post(f"{self.base_url}{endpoint}", **kwargs)

    #def get_category(self, endpoint,category_id=0):
    #    
    #    cookies=config.COOKIES['MoodleSession']
    #    print("Cookies: ",cookies)
    #    sesskey = self.get_sesskey()
    #    print("sesskey: ",sesskey)
    #    COURSES_URL=f"{self.base_url}{endpoint}"
    #    print("COURSES_URL: ",COURSES_URL)
#
    #    data = {
    #        "categoryid": category_id,
    #        "depth": 5,
    #        "showcourses": 1000,
    #        "type": 0
    #    }
#
    #    headers = {
    #        "User-Agent": "Mozilla/5.0",
    #        "X-Requested-With": "XMLHttpRequest",
    #        "Referer": f"{self.base_url}/course/index.php"
    #    }
#
    #    resp = self.session.post(COURSES_URL, data=data, headers=headers)
#
    #    return resp.text
    
    def get_category(self, endpoint, category_id=0, page=0):
        
        cookies=self.cookies['MoodleSession']
        #print("Cookies: ",cookies)
        sesskey = self.get_sesskey()
        #print("sesskey: ",sesskey)

        COURSES_URL = f"{self.base_url}{endpoint}"
        print(COURSES_URL)
        data = {
            "categoryid": category_id,
            "browse": "courses",
            "perpage": 20,
            "page": page
        }

        headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/course/index.php"
        }

        resp = self.session.post(
            COURSES_URL,
            data=data,
            headers=headers
        )

        return resp.text
