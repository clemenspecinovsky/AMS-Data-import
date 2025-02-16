import os
import json

import dateutil
import requests
from linkedin_api import Linkedin

def get_page_value(content, findstr, endstr):
    ret = None
    start = content.find(findstr)
    if start>0:
        end = content.find(endstr,start+len(findstr))
        if end>start:
            ret = content[start+len(findstr):end]
    return ret

def get_page_instance(content):
    return get_page_value(content,  '<meta name="pageInstance" content="', '">')

def get_sid(content):
    return get_page_value(content,  '<input name="sIdString" value="', '" type="hidden">')

def get_loginparam(content):
    return get_page_value(content,  '<input name="loginCsrfParam" value="', '" type="hidden">')


def linkedin_login(usr, pwd):
    session = requests.Session()
    url = "https://www.linkedin.com/checkpoint/lg/login"

    req1 = session.get(url)
    page_instance = get_page_instance(req1.text)
    sid = get_sid(req1.text)
    csrf = get_loginparam(req1.text)

    session_id = req1.cookies.get("JSESSIONID")
    session_id = session_id[1:-1]
    url = "https://www.linkedin.com/checkpoint/lg/login-submit"
    data = {"session_key":usr,
            "session_password":pwd,
            "controlId":"d_checkpoint_lg_consumerLogin-login_submit_button",
            "csrfToken":session_id,
            "sIdString":sid,
            "parentPageKey":"d_checkpoint_lg_consumerLogin",
            "pageInstance":page_instance,
            "trk":"guest_homepage-basic_nav-header-signin",
            "authUUID":"",
            "loginCsrfParam":csrf,
            "loginFailureCount":"0",
            "ac": "0",
            "pkSupported":"true",
            "fp_data": "default",
            "_d": "d",
            "showGoogleOneTapLogin": "false",
            "showAppleLogin": "false",
            "showMicrosoftLogin": "false",
            }
    #data = "\n".join([f'{e[0]}:"{e[1]}"' for e in data_dict.items()])
    header = {"Content-Type":"application/x-www-form-urlencoded",
              "Referer":"https://www.linkedin.com/login?fromSignIn=true&trk=guest_homepage-basic_nav-header-signin",
              "Origin":"https://www.linkedin.com",
              "Host":"www.linkedin.com",
              "DTN":"1",
              "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"}

    req = session.request("POST", url, data=data, headers=header)
    assert req.status_code == 200
    assert req.text.find("Security Verification")==-1

    return session, session_id

def get_jobs(session, session_id):
    ret = []
    url = "https://www.linkedin.com/voyager/api/graphql?variables=(start:0,query:(flagshipSearchIntent:SEARCH_MY_ITEMS_JOB_SEEKER,queryParameters:List((key:cardType,value:List(APPLIED)))))&queryId=voyagerSearchDashClusters.cd5ee9d14d375bf9ca0596cfe0cbb926"

    header = {"Accept": "application/vnd.linkedin.normalized+json+2.1",
              "Referer": "https://www.linkedin.com/login?fromSignIn=true&trk=guest_homepage-basic_nav-header-signin",
              "Origin": "https://www.linkedin.com",
              "csrf-token":session_id,
              "Host": "www.linkedin.com",
              "DTN": "1",
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"}

    req = session.get(url, headers=header)
    data = json.loads(req.text)
    items = [item["item"]["*entityResult"] for item in data["data"]["data"]["searchDashClustersByAll"]["elements"][0]["items"]]
    jobcards = []
    for item in items:
        assert item.startswith("urn:li:fsd_entityResultViewModel:(urn:li:jobPosting:")
        assert item.endswith(",SEARCH_MY_ITEMS_JOB_SEEKER,DEFAULT)")
        jobcards.append(item[34:-36])

    url2 = f"https://api.linkedin.com/v2/jobApplications?q=jobPostings&jobPostings={jobcards[0]}"
    req2 = session.get(url2, headers=header)

    url3 = f"https://api.linkedin.com/v2/jobApplications?q=jobPostings&jobPostings={jobcards[1]}"
    req3 = session.get(url3, headers=header)

    url4 = f"https://api.linkedin.com/v2/jobApplications?q=jobPostings&jobPostings={jobcards[2]}"
    req4 = session.get(url4, headers=header)

    for ii in data["included"]:
        if "template" in ii and ii["template"]=="UNIVERSAL":
            assert ii["trackingUrn"] in jobcards


    return ret

def split_csv_line(line, seperator):
    ret = []
    cur_pos = 0
    while cur_pos<len(line):
        if line[cur_pos]=='"':
            end_pos = line.find('"',cur_pos+1)
            while end_pos+1<len(line) and line[end_pos+1]=='"':
                end_pos = line.find('"',end_pos+2)
                if end_pos==-1:
                    end_pos = len(line)

            item = line[cur_pos+1:end_pos]
            end_pos +=1
            if len(line)>end_pos:
                assert line[end_pos]==seperator
                end_pos +=1
        else:
            end_pos = line.find(seperator, cur_pos)
            if end_pos==-1:
                end_pos = len(line)
            item = line[cur_pos:end_pos]
            end_pos += 1
        cur_pos = end_pos
        ret.append(item)
    if cur_pos==len(line) and line[cur_pos-1]==seperator:
        ret.append(None)
    return ret

def parse_csv(lines, seperator):
    header = None
    elements = []
    for line_idx, line in enumerate(lines):
        if line.endswith("\n"):
            line = line[:-1]
        if len(line)>0:
            #print(f"{line_idx}: {line}")
            if header is None:
                header = split_csv_line(line, seperator)
            else:
                element = split_csv_line(line, seperator)
                assert len(element)==len(header)
                elements.append(element)
    return header, elements
def read_csv(filename):
    with open(filename, 'r', encoding='UTF-8') as file:
        lines = file.readlines()
    header, elements = parse_csv(lines, ",")
    return header, elements

def get_jobs_from_csv(header, elements, column_names):
    extract_elements = [header.index(col) for col in column_names]
    ret = []
    for element in elements:
        extract = []
        for idx in extract_elements:
            v = element[idx].strip()
            if idx==0:
                v = dateutil.parser.parse(v)
            extract.append(v)
        ret.append(extract)
    return ret


def get_linkedin_jobs_internal(filename, column_names):
    header, elements = read_csv(filename)
    ret = get_jobs_from_csv(header, elements, column_names)
    return ret

def get_linkedin_jobs(filename):
    column_names = ["Application Date", "Company Name", "Job Title", "Job Url"]
    return get_linkedin_jobs_internal(filename, column_names)

def get_linkedin_savedjobs(filename):
    column_names = ["Saved Date", "Company Name", "Job Title", "Job Url"]
    return get_linkedin_jobs_internal(filename, column_names)

def get_all_linkedin_jobs():
    export_dir = os.path.dirname(__file__)
    jobs_applied = get_linkedin_jobs(export_dir+"/Job Applications.csv")
    jobs_saved = get_linkedin_savedjobs(export_dir+"/Saved Jobs.csv")
    total_jobs = jobs_applied + jobs_saved
    total_jobs.sort()
    return total_jobs


def main():
    export_dir = "C:/Users/Peci/Downloads/"
    user = "clemens.pecinovsky@gmx.at"
    pwd = "Scoopex1"

    session, session_id = linkedin_login(user, pwd)
    job_list = get_jobs(session, session_id)

    #api = Linkedin(user, pwd)
    #res = api._fetch(
    #    f"/graphql?variables=(start:0,query:(flagshipSearchIntent:SEARCH_MY_ITEMS_JOB_SEEKER,queryParameters:List((key:cardType,value:List(APPLIED)))))&queryId=voyagerSearchDashClusters.cd5ee9d14d375bf9ca0596cfe0cbb926")
    #data = res.json()

    return 0


if __name__ == "__main__":
    retval = main()

    print("exited with return code %s" % retval)
    exit(retval)
