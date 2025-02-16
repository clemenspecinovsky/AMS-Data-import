import collections
import time
from datetime import datetime
import re

import dateutil
import requests
from exportJobsLinkedIn import get_all_linkedin_jobs, parse_csv, get_jobs_from_csv
from jobs.exportJobsingamejobs import get_all_ingamejob_jobs


def get_page_value(content, findstr, endstr):
    ret = None
    start = content.find(findstr)
    if start>0:
        end = content.find(endstr,start+len(findstr))
        if end>start:
            ret = content[start+len(findstr):end]
    return ret

def get_view_state(content):
    return get_page_value(content,  '<input type="hidden" name="javax.faces.ViewState" value="', '" autocomplete="off" />')

def get_eams_track(content):
    return get_page_value(content,  'method="post" action="/eams-sfa-account/p/EsaSEigenbewerbGes.jsf?eamsTrack=','" enctype="')

def eams_login(usr, pwd):
    url = "https://www.e-ams.at/eams-sfa-account/p/j_security_check"
    session = requests.Session()

    header = {  "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Content-Type":"application/x-www-form-urlencoded",
                "Referer":"https://www.e-ams.at/eams-sfa-account/p/",
                "DTN":"1",
                "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
                "Host":"www.e-ams.at",
                "Origin": "https://www.e-ams.at",
                "Sec-Fetch-Dest":"document",
                "Sec-Fetch-Mode":"navigate",
                "Sec-Fetch-Site":"same-origin",
                "Sec-Fetch-User":"?1",
                "Sec-GPC":"1",
                "Upgrade-Insecure-Requests":"1"
                }

    data = {"j_username":usr, "j_password":pwd}

    req1 = session.get( url, headers=header)
    req = session.request("POST", url, data=data, headers=header)
    #assert req.status_code == 200
    assert req.text.find("Mein eAMS ")>0

    url2 = "https://www.e-ams.at/eams-sfa-account/p/index.jsf"
    req2 = session.get( url2, headers=header)
    assert req2.text.find("Eingeloggt als:") > 0
    return session

def eams_add_job(session, date, job, company, contact, info, note, is_open):
    url = "https://www.e-ams.at/eams-sfa-account/p/index.jsf"

    header = {  "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Content-Type":"application/x-www-form-urlencoded",
                "Referer":"https://www.e-ams.at/eams-sfa-account/p/",
                "DTN":"1",
                "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
                "Host":"www.e-ams.at",
                "Origin": "https://www.e-ams.at",
                "Sec-Fetch-Dest":"document",
                "Sec-Fetch-Mode":"navigate",
                "Sec-Fetch-Site":"same-origin",
                "Sec-Fetch-User":"?1",
                "Sec-GPC":"1",
                "Upgrade-Insecure-Requests":"1"
                }

    req = session.get(url, headers=header)
    assert req.text.find("Eingeloggt als:")>0
    view_state = get_view_state(req.text)
    assert view_state is not None

    url2 = "https://www.e-ams.at/eams-sfa-account/p/EsaSEigenbewerb.jsf"
    data = {
        "pnav_SUBMIT": "1",
        "javax.faces.ViewState": view_state,
        "targetForm": "EsaSEigenbewerbGes.jsf",
        "pnav:_idcl": "pnav:bewerbungsverlauf"
    }
    req2 = session.get(url2, headers=header)
    view_state2 = get_view_state(req2.text)
    assert view_state2 is not None

    #eams_track1 = get_eams_track(req.text)
    #assert eams_track1 is not None

    #url2 = f"https://www.e-ams.at/eams-sfa-account/p/EsaSEigenbewerb.jsf?eamsTrack={eams_track1}"
    header["Referer"]= url2
    data = { "form:importDocEamsEigenbewerbung-erstellung0Date": date,
            "form:importDocEamsEigenbewerbung-betrieb": company,
            "form:importDocEamsEigenbewerbung-kontaktperson": contact,
            "form:importDocEamsEigenbewerbung-beschaeftigung": job,
            "form:importDocEamsEigenbewerbung-stelleninfo": info,
            "form:importDocEamsEigenbewErfolgt-eigenbewErfolgt0Code": "O",
            "form:importDocEamsEigenbewStand-eigenbewStand0Code": ("O" if is_open else"A"),
            "form:importDocEamsEigenbewerbung-notizen": note,
            "form:button-preview": "Weiter",
            #"form:j_id_3w_2_v_e_2:__addDoc_": "Anhang+hinzufügen",
            "form_SUBMIT": "1",
            "javax.faces.ViewState": view_state2
             }

    req3 = session.request("POST", url2, data=data, headers=header)
    assert req3.status_code == 200
    view_state3 = get_view_state(req3.text)

    data = {"form:button-submit": "Speichern",
            "form_SUBMIT": "1",
            "javax.faces.ViewState": view_state3
            }
    req4 = session.request("POST", url2, data=data, headers=header)
    assert req3.status_code == 200

def get_job_list_from_page(content, page_no):
    ret = None
    eigen_header = "<h2>Liste der Eigenbewerbungen</h2>"
    cur_pos = content.find(eigen_header)
    assert cur_pos>0

    search1 = "<td class=\"column-date first-child\">"
    search2 = '<td'
    search3 = '</td>'
    cur_pos = 0
    while cur_pos < len(content):
        line_start = content.find(search1, cur_pos)
        if line_start>0:
            line_end = content.find(search1, line_start+1)
            if line_end<0:
                line_end = len(content)
            elements = []
            while line_start < line_end:
                line_start = content.find(search2, line_start)
                if line_start>=0:
                    column_start = content.find(">", line_start) + 1
                    column_end = content.find(search3, column_start)
                    element = content[column_start:column_end].strip()
                    line_start = column_end + len(search3)
                    elements.append(element)
                else:
                    line_start = line_end
            #if len(elements)!=9:
            #    print("no")
            assert len(elements)==9 or len(elements)==8
            if ret is None:
                ret = []

            job_date = elements[1]
            job_title = elements[4]
            job_company = elements[2]
            job_contact = None if len(elements[3])==0 else elements[3]
            link_search = "<input id=\""
            link_start = elements[7].find(link_search)
            assert link_start >= 0
            link_start += len(link_search)
            link_end = elements[7].find("\"", link_start)
            link = elements[7][link_start:link_end]
            assert link.endswith(":cbid")
            link = link[:-5] + ":details"

            ret.append((job_date, job_title, job_company, page_no, link))

            cur_pos = line_end
        else:
            cur_pos = len(content)
    return ret

def get_jobs_next_page(content, first_page=False):
    ret = None
    eigen_header = "<h2>Liste der Eigenbewerbungen</h2>"
    cur_pos = content.find(eigen_header)
    assert cur_pos>0
    if first_page:
        search = "title=\"zur ersten Seite\">"
    else:
        search = "title=\"zur nächsten Seite\">"
    search2 = "<a href=\""
    line_end = content.find(search, cur_pos)
    if line_end>0:
        line_start = content.rfind(search2, cur_pos, line_end)
        if line_start > 0:
            line_start += len(search2)
            line_end = content.find("\"", line_start)
            link = content[line_start:line_end]
            ret = link
    return ret

def get_value_from_line(line):
    search = "</span>"
    end_pos = line.find(search)
    assert end_pos>0
    start_pos = line.rfind(">", 0, end_pos)
    assert start_pos > 0
    return line[start_pos+1: end_pos]

def get_job_detail(content):
    ret = None
    search = "<table class=\"vtable2\">"
    search2 = "</table>"
    cur_pos = content.find(search)
    assert cur_pos >0
    cur_pos += len(search)
    end_pos = content.find(search2, cur_pos)
    assert end_pos > 0

    search3 = "<th"
    search4 = "</th>"
    search5 = "<td"
    search6 = "</td>"
    while cur_pos < end_pos:
        key_start = content.find(search3, cur_pos)
        if key_start == -1 or key_start>end_pos:
            cur_pos = len(content)
        else:
            key_end = content.find(search4, key_start)
            val_start = content.find(search5, key_end)
            val_end = content.find(search6, val_start)
            key = get_value_from_line(content[key_start:key_end])
            val = get_value_from_line(content[val_start:val_end])
            if ret is None:
                ret = {}
            ret[key] = val
            cur_pos = val_end

    return ret

def eams_get_jobs_list(session):
    url = "https://www.e-ams.at/eams-sfa-account/p/index.jsf"

    header = {  "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Content-Type":"application/x-www-form-urlencoded",
                "Referer":"https://www.e-ams.at/eams-sfa-account/p/",
                "DTN":"1",
                "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
                "Host":"www.e-ams.at",
                "Origin": "https://www.e-ams.at",
                "Sec-Fetch-Dest":"document",
                "Sec-Fetch-Mode":"navigate",
                "Sec-Fetch-Site":"same-origin",
                "Sec-Fetch-User":"?1",
                "Sec-GPC":"1",
                "Upgrade-Insecure-Requests":"1"
                }

    req = session.get(url, headers=header)
    assert req.text.find("Eingeloggt als:")>0
    view_state = get_view_state(req.text)
    assert view_state is not None

    url2 = "https://www.e-ams.at/eams-sfa-account/p/EsaSEigenbewerbGes.jsf"
    data = {
        "pnav_SUBMIT": "1",
        "javax.faces.ViewState": view_state,
        "targetForm": "EsaSEigenbewerbGes.jsf",
        "pnav:_idcl": "pnav:bewerbungsverlauf"
    }
    req2 = session.request("POST", url2, data=data, headers=header)
    header["Filename"] = "eams-sfa-account/p/EsaSEigenbewerbGes.jsf"
    req3 = session.get(url2, headers=header)

    page_no = 0
    job_list = get_job_list_from_page(req3.text, page_no)
    job_next_page = get_jobs_next_page(req3.text)

    while job_next_page is not None:
        page_no += 1
        url3 = "https://www.e-ams.at" + job_next_page
        req3 = session.get(url3, headers=header)
        req4 = session.get(url2, headers=header)
        job_list_tmp = get_job_list_from_page(req4.text, page_no)
        if job_list_tmp is not None:
            job_list.extend(job_list_tmp)
        job_next_page = get_jobs_next_page(req4.text)

    if page_no>0:
        first_page = get_jobs_next_page(req4.text, True)
        url3 = "https://www.e-ams.at" + first_page
        req3 = session.get(url3, headers=header)

    return job_list

def eams_update_job(session, jobs_list, job):
    #find jobs in list
    job_details = []
    for job_link in jobs_list:
        if job_link[1]==job[1] and job_link[2]==job[2]:
            if job_link[0]!=job[0]:
                print("no!")
            job_details.append(job_link)
    num_pages = max([e[3] for e in jobs_list]) + 1

    url = "https://www.e-ams.at/eams-sfa-account/p/index.jsf"

    header = {  "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Content-Type":"application/x-www-form-urlencoded",
                "Referer":"https://www.e-ams.at/eams-sfa-account/p/",
                "DTN":"1",
                "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
                "Host":"www.e-ams.at",
                "Origin": "https://www.e-ams.at",
                "Sec-Fetch-Dest":"document",
                "Sec-Fetch-Mode":"navigate",
                "Sec-Fetch-Site":"same-origin",
                "Sec-Fetch-User":"?1",
                "Sec-GPC":"1",
                "Upgrade-Insecure-Requests":"1"
                }

    req = session.get(url, headers=header)
    assert req.text.find("Eingeloggt als:")>0
    view_state = get_view_state(req.text)
    assert view_state is not None

    url2 = "https://www.e-ams.at/eams-sfa-account/p/EsaSEigenbewerbGes.jsf"
    data = {
        "pnav_SUBMIT": "1",
        "javax.faces.ViewState": view_state,
        "targetForm": "EsaSEigenbewerbGes.jsf",
        "pnav:_idcl": "pnav:bewerbungsverlauf"
    }
    req2 = session.request("POST", url2, data=data, headers=header)
    header["Filename"] = "eams-sfa-account/p/EsaSEigenbewerbGes.jsf"
    req3 = session.get(url2, headers=header)

    if len(job_details) == 0:
        print(f"Error job {job} not found in system.")
    else:
        #peci could happen that several jobs are found. might need a fix here
        if len(job_details) > 1:
            print("no")
        assert len(job_details)==1

        job_detail = job_details[0]
        #goto page:
        cur_page = 0

        while cur_page < job_detail[3]:
            cur_page += 1
            job_next_page = get_jobs_next_page(req3.text)
            url3 = "https://www.e-ams.at" + job_next_page
            req3 = session.get(url3, headers=header)
            req3 = session.get(url2, headers=header)

        first_page = None
        if job_detail[3]>0:
            first_page = get_jobs_next_page(req3.text, True)

        # load up detail page
        view_state = get_view_state(req3.text)
        assert view_state is not None
        data = {
            job_detail[4]: "Details",
            "list_SUBMIT": "1",
            "javax.faces.ViewState": view_state,
        }

        req4 = session.request("POST", url2, data=data, headers=header)
        job_detail_data = get_job_detail(req4.text)
        assert job_detail_data["Datum"]==job[0]
        assert job_detail_data["Firma/Betrieb"] == job[2]
        assert job_detail_data["Beschäftigung als"] == job[1]
        assert job_detail_data["Notizen"] == job[5]
        assert job_detail_data["Wie erfolgte die Bewerbung"] == "online"
        assert job_detail_data["Woher kam die Stelleninfo"] == job[4]

        if job_detail_data["Status der Bewerbung"]!="Absage" and job_detail_data["Status der Bewerbung"]!="Antwort des Betriebes offen":
            print(f"unbekannter status {job_detail_data['Status der Bewerbung']}")
        is_open_ams = job_detail_data["Status der Bewerbung"]!="Absage"

        #currently only isopen change is supported, so must be different
        assert is_open_ams != job[6]

        view_state = get_view_state(req4.text)
        assert view_state is not None
        url3 = "https://www.e-ams.at/eams-sfa-account/p/EsaSEigenbewerb.jsf"
        data = {
            "form:button-edit": "Bearbeiten",
            "form_SUBMIT": "1",
            "javax.faces.ViewState": view_state,
        }
        header["Filename"] = "/eams-sfa-account/p/EsaSEigenbewerb.jsf"
        req5 = session.request("POST", url3, data=data, headers=header)
        view_state2 = get_view_state(req5.text)
        assert view_state2 is not None
        date, job_title, company, contact, info, note, is_open = job
        data = { "form:importDocEamsEigenbewerbung-erstellung0Date": date,
                "form:importDocEamsEigenbewerbung-betrieb": company,
                "form:importDocEamsEigenbewerbung-kontaktperson": contact,
                "form:importDocEamsEigenbewerbung-beschaeftigung": job_title,
                "form:importDocEamsEigenbewerbung-stelleninfo": info,
                "form:importDocEamsEigenbewErfolgt-eigenbewErfolgt0Code": "O",
                "form:importDocEamsEigenbewStand-eigenbewStand0Code": ("O" if is_open else"A"),
                "form:importDocEamsEigenbewerbung-notizen": note,
                "form:button-preview": "Weiter",
                #"form:j_id_3w_2_v_e_2:__addDoc_": "Anhang+hinzufügen",
                "form_SUBMIT": "1",
                "javax.faces.ViewState": view_state2
                 }

        req6 = session.request("POST", url3, data=data, headers=header)
        assert req6.status_code == 200
        view_state3 = get_view_state(req6.text)

        data = {"form:button-submit": "Speichern",
                "form_SUBMIT": "1",
                "javax.faces.ViewState": view_state3
                }
        req7 = session.request("POST", url3, data=data, headers=header)
        assert req7.status_code == 200
        assert req7.text.find("Die Eingabe Ihrer Daten war erfolgreich.")>0

        if first_page is not None:
            url3 = "https://www.e-ams.at" + first_page
            req3 = session.get(url3, headers=header)


def eams_get_jobs_internal(session):
    url = "https://www.e-ams.at/eams-sfa-account/p/index.jsf"

    header = {  "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Content-Type":"application/x-www-form-urlencoded",
                "Referer":"https://www.e-ams.at/eams-sfa-account/p/",
                "DTN":"1",
                "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
                "Host":"www.e-ams.at",
                "Origin": "https://www.e-ams.at",
                "Sec-Fetch-Dest":"document",
                "Sec-Fetch-Mode":"navigate",
                "Sec-Fetch-Site":"same-origin",
                "Sec-Fetch-User":"?1",
                "Sec-GPC":"1",
                "Upgrade-Insecure-Requests":"1"
                }

    req = session.get(url, headers=header)
    assert req.text.find("Eingeloggt als:")>0
    view_state = get_view_state(req.text)
    assert view_state is not None

    url2 = "https://www.e-ams.at/eams-sfa-account/p/EsaSEigenbewerb.jsf"
    data = {
        "pnav_SUBMIT": "1",
        "javax.faces.ViewState": view_state,
        "targetForm": "EsaSEigenbewerbGes.jsf",
        "pnav:_idcl": "pnav:bewerbungsverlauf"
    }
    req2 = session.get(url2, headers=header)
    view_state2 = get_view_state(req2.text)
    assert view_state2 is not None

    url3 = "https://www.e-ams.at/eams-sfa-account/Print/csv?id=eigenbewerb"
    req3 = session.get(url3, headers=header)

    csv_data = req3.text
    lines = csv_data.split("\n")
    header, elements = parse_csv(lines, ";")

    column_names = ["Datum", "Woher kam die Stelleninfo", "Firma/Betrieb", "Beschaeftigung als", "Notizen", "Status der Bewerbung"]
    ret = get_jobs_from_csv(header, elements, column_names)

    for idx, job in enumerate(ret):
        if job[5]!="Absage" and job[5]!="Antwort des Betriebes offen":
            print(f"unbekannter status {job[5]} in line {idx}")
        is_open = job[5]!="Absage"
        ret[idx][5] = is_open
    return ret

def fix_job_title(job_title):
    if len(job_title) > 40:
        if job_title.find("(") > 0:
            idx = job_title.find("(")
            job_title = job_title[0:idx]
        elif job_title.find(",") > 0:
            idx = job_title.find(",")
            job_title = job_title[0:idx]
        else:
            job_title = job_title[0:40]
    job_title = job_title.replace(chr(1057), "C")

    # match left and right single quotes
    single_quote_expr = re.compile(r'[\u2018\u2019]', re.U)
    # match all non-basic latin unicode
    unicode_chars_expr = re.compile(r'[\u0080-\uffff]', re.U)
    job_title = single_quote_expr.sub("'", job_title, re.U)
    job_title = unicode_chars_expr.sub("", job_title, re.U)

    return job_title.strip()

def update_changed_jons(usr, pwd, jobs):
    session = eams_login(usr, pwd)
    jobs_list = eams_get_jobs_list(session)

    for idx, job in enumerate(jobs):
        date = job[0].strftime("%d.%m.%Y")
        job_title = fix_job_title(job[3])
        contact = None
        company = fix_job_title(job[2])
        info = job[1]
        note = job[4]
        is_open = job[5]
        print(f"{idx}: updating '{date}' '{job_title}' '{company}' '{note}' '{info}' {is_open}")
        eams_update_job(session, jobs_list, (date, job_title, company, contact, info ,note, is_open))

def add_ams_jobs(usr, pwd, jobs):
    session = eams_login(usr, pwd)

    for idx, job in enumerate(jobs):
        date = job[0].strftime("%d.%m.%Y")
        job_title = fix_job_title(job[3])
        contact = None
        company = fix_job_title(job[2])
        info = job[1]
        note = job[4]
        is_open = job[5]
        print(f"{idx}: adding '{date}' '{job_title}' '{company}' '{note}' '{info}' {is_open}")
        eams_add_job(session, date, job_title, company, contact, info ,note, is_open)
        #time.sleep(2)

def get_ams_jobs(usr, pwd):
    session = eams_login(usr, pwd)
    jobs = eams_get_jobs_internal(session)
    return jobs

def filter_jobs(jobs, ams_jobs):
    link_list_ams = dict([(j[4], idx) for idx, j in enumerate(ams_jobs)])
    assert len(link_list_ams) == len(ams_jobs)
    missing = []
    changed = []
    for job in jobs:
        if job[4] not in link_list_ams:
            missing.append(job)
        else:
            ams_job = ams_jobs[link_list_ams[job[4]]]
            if not (ams_job[1] == job[1] and ams_job[2] == fix_job_title(job[2]) and \
                ams_job[3] == fix_job_title(job[3])):
                print("no")
            assert(ams_job[1] == job[1] and ams_job[2] == fix_job_title(job[2]) and \
                ams_job[3] == fix_job_title(job[3]))
            if ams_job[0].date()!=job[0].date() or ams_job[4:]!=job[4:]:
                changed.append(job)
    return missing, changed

def is_job_open(jobdate):
    time_between_insertion = datetime.now() - jobdate
    is_open = time_between_insertion.days<14
    return is_open

def main():
    with open('settings.ini') as fd:
        settings = fd.read()
        exec(settings)

    jobs = ([[job[0],"linkedIn"]+job[1:]+[is_job_open(job[0])] for job in get_all_linkedin_jobs()] +
            [[job[0],"ingamejob"]+job[1:]+[is_job_open(job[0])] for job in get_all_ingamejob_jobs()])
    jobs.sort(reverse=True)

    link_list = [j[4] for j in jobs]
    duplicated = [item for item, count in collections.Counter(link_list).items() if count > 1]
    #remove duplicated
    if len(duplicated)>0:
        for duplicate in duplicated:
            idx = link_list.index(duplicate)
            del jobs[idx]
            del link_list[idx]

        link_list = [j[4] for j in jobs]
        duplicated = [item for item, count in collections.Counter(link_list).items() if count > 1]
        assert len(duplicated)==0

    #assert len(link_list)== len(set(link_list))

    ams_jobs = get_ams_jobs(usr, pwd)

    new_jobs, changed_jobs = filter_jobs(jobs, ams_jobs)
    if len(changed_jobs)>0:
        update_changed_jons(usr, pwd, changed_jobs)

    if len(new_jobs)>0:
        add_ams_jobs(usr, pwd, new_jobs)

    return 0


if __name__ == "__main__":
    retval = main()

    print("exited with return code %s" % retval)
    exit(retval)
