from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Tuple
from settings import *
from utils.log import log
import atexit
import os
import re
import requests
import shutil
import tempfile

BASE_DIR = Path(__file__).resolve().parent
EXTRA_CA_CERT = BASE_DIR / "certs" / "SectigoPublicServerAuthenticationCAOVR36.pem"
proxy = {'http': 'http://127.0.0.1:8080', 'https': 'http://127.0.0.1:8080'} # burp debug

def build_ca_bundle() -> str:
    ca_bundle = Path(
        os.environ.get("REQUESTS_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
        or requests.certs.where()
    )

    if not EXTRA_CA_CERT.exists():
        return str(ca_bundle)

    fd, bundle_path = tempfile.mkstemp(prefix="its-ipd-ca-", suffix=".pem")
    with os.fdopen(fd, "wb") as output:
        for cert_path in (ca_bundle, EXTRA_CA_CERT):
            with cert_path.open("rb") as cert:
                shutil.copyfileobj(cert, output)
            output.write(b"\n")

    atexit.register(lambda: Path(bundle_path).unlink(missing_ok=True))
    return bundle_path

def check_session() -> bool:
    for part in COOKIE.split(";"):
        key, value = part.strip().split("=", 1)
        client.cookies.set(key, value)
    res = client.get("https://akademik.its.ac.id/home.php", allow_redirects=True)
    if 'Microsoft' in res.text or 'human visitor' in res.text:
        log.error('Provide a valid cookie')
        exit(1)
    global soup, SEMESTER_TERM, TAHUN_AJARAN
    soup = BeautifulSoup(res.text, 'html.parser')
    log.success('Session is valid')
    # auto get term and year
    targets = soup.find('td', string=lambda t: t and 'Periode:' in t and 'Tanggal:' in t).encode().split(b'\t\t')
    SEMESTER_TERM = '1' if b'Gasal' in targets[1] else '2'
    TAHUN_AJARAN = targets[1].split(b' ')[-1].split(b'/')[0]
    return True

def get_courses() -> Tuple[List[str], List[str]]:
    client.get("https://akademik.its.ac.id/home.php", allow_redirects=True)
    res = client.get("https://akademik.its.ac.id/ipd_kuesionermk.php", allow_redirects=True)

    soup = BeautifulSoup(res.text, 'html.parser')
    value_pattern = r'<option\s+[^>]*value=["\']([^"\']+)["\']'
    str_pattern = r'<option[^>]*value="[^"]+"[^>]*>(.*?)</option>'

    try:
        select = soup.find('select', {'name': 'mk_kuesioner', 'id': 'mk_kuesioner'})
        courses_code = re.findall(value_pattern, str(select ))
        courses_detail = re.findall(str_pattern, str(select))
    except Exception as e:
        log.error(f'Failed to parse the course list: {e}')
        exit(1)
    
    for i in range(len(courses_code)):
        log.success(f'{courses_code[i]}: {courses_detail[i]}')
    return courses_code, courses_detail

def change_to_course_ipd(code) -> bool:
    res = client.post("https://akademik.its.ac.id/ipd_kuesionermk.php", data={
        "semesterTerm": SEMESTER_TERM,
        "thnAjaran": TAHUN_AJARAN,
        "act": "mkchange",
        "key": "",
        "scroll": "",
        "page": "1",
        "sort": "1",
        "filter": "",
        "mk_kuesioner": code
    })

    if res.status_code != 200:
        log.error('failed to change course: %s', code)
        exit(1)
    
    if 'Anda sudah mengisi kuesioner untuk matakuliah ini' in res.text:
        return False
    return True

def submit_course_ipd():
    res = client.post("https://akademik.its.ac.id/ipd_kuesionermk.php", data={
        "act": "inputKuesioner",
        "MK1": DEFAULT_PENILAIAN,
        "MK2": DEFAULT_PENILAIAN,
        "MK3": DEFAULT_PENILAIAN,
        "MK4": DEFAULT_PENILAIAN,
        "MK5": DEFAULT_PENILAIAN,
        "MK6": DEFAULT_PENILAIAN,
        "MK7": DEFAULT_PENILAIAN,
        "MK8": DEFAULT_PENILAIAN,
        "MK9": DEFAULT_PENILAIAN,
        "MK10": DEFAULT_PENILAIAN,
        "txtKomentar": "",
        "chkPermanent": "1",
        "button": "SIMPAN"
    })

def get_lecturer_list(code) -> List[str]:
    # print(target.encode().split(b'\t\t'))
    res = client.post("https://akademik.its.ac.id/ipd_kuesionermk.php", data={
        "semesterTerm": SEMESTER_TERM,
        "thnAjaran": TAHUN_AJARAN,
        "act": "mkchange",
        "key": "",
        "scroll": "",
        "page": "1",
        "sort": "1",
        "filter": "",
        "mk_kuesioner": code
    })

    soup = BeautifulSoup(res.text, 'html.parser')
    href_pattern = r'href="([^"]+)"'

    try:
        form = soup.find('form', {'name': 'form2', 'id': 'form2'})
        lecturer_path = re.findall(href_pattern, str(form))

        table = form.find('table', {'class': 'FilterBox'})
        entries = table.find_all('tr')
        for entry in entries:
            if 'Isi Kuesioner' in entry.text:
                continue
            lecturer_name = entry.find('td').text.split("-")[1].strip()
            log.success("IPD dosen %s sudah terisi", lecturer_name)

        return lecturer_path
    except Exception as e:
        log.error(f'Failed to parse the lecturer list: {e}')
        exit(1)

def change_to_lecturer_ipd(path) -> bool:
    res = client.get(f'https://akademik.its.ac.id/{path}', allow_redirects=True)

    soup = BeautifulSoup(res.text, 'html.parser')
    h3_pattern = pattern = r'<h3>(.*?)</h3>'

    try:
        form = soup.find('form', {'name': 'form2', 'id': 'form2'})
        lecturer_name = re.findall(h3_pattern, str(form))
    except Exception as e:
        log.error(f'Failed to parse the lecturer page: {e}')
        exit(1)

    if 'Anda sudah mengisi kuesioner untuk dosen di matakuliah ini' in res.text:
        log.success("IPD dosen %s sudah terisi", lecturer_name[1])
        return False
    log.info("mengisi IPD dosen %s", lecturer_name[1])
    return True

def submit_lecturer_ipd():
    res = client.post("https://akademik.its.ac.id/ipd_kuesionerdosen.php", data={
        "act": "inputKuesioner",
        "DO1": DEFAULT_PENILAIAN,
        "DO2": DEFAULT_PENILAIAN,
        "DO3": DEFAULT_PENILAIAN,
        "DO4": DEFAULT_PENILAIAN,
        "DO5": DEFAULT_PENILAIAN,
        "DO6": DEFAULT_PENILAIAN,
        "DO7": DEFAULT_PENILAIAN,
        "DO8": DEFAULT_PENILAIAN,
        "DO9": DEFAULT_PENILAIAN,
        "DO10": DEFAULT_PENILAIAN,
        "txtKomentar": "",
        "chkPermanent": "1",
        "button": "SIMPAN"
    })

def main():
    check_session()
    
    codes, details = get_courses()

    # ipd mata kuliah
    for i, code in enumerate(codes):
        if(change_to_course_ipd(code)):
            log.info("mengisi IPD mata kuliah %s", details[i].split("-")[1].strip())
            submit_course_ipd()
        else:
            log.success("IPD mata kuliah %s sudah terisi", details[i].split("-")[1].strip())

    # ipd dosen
    for code in codes:
        lecturers = get_lecturer_list(code)
        for lecturer in lecturers:
            if(change_to_lecturer_ipd(lecturer)):
                submit_lecturer_ipd()

if __name__ == '__main__':
    global client
    client = requests.Session()
    client.verify = build_ca_bundle()
    main()
