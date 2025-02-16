import os

import dateutil


def get_html_text(content):
    ret = None
    start = content.find(">")
    if start>0:
        end = content.find("</", start)
        if end>0:
            ret = content[start+1:end]
    return ret


def get_html_link(content):
    ret = None
    start = content.find('href="')
    if start > 0:
        start += 6
        end = content.find('"', start)
        if end > 0:
            ret = content[start:end]
    return ret

def extract_job(elements):
    date = dateutil.parser.parse(elements[1].strip())
    company_name = get_html_text(elements[3]).strip()
    job_title = get_html_text(elements[2]).strip()
    job_url = get_html_link(elements[2])

    return [date, company_name, job_title, job_url]

def get_htlm_table_content(filename):
    with open(filename, 'r', encoding='UTF-8') as file:
        content = file.read()

    search1 = '<button type="button" class="v-icon notranslate v-data-table__expand-icon v-icon--link mdi mdi-chevron-down theme--light"></button>'
    search2 = '<td class="text-start">'
    search3 = '</td>'

    ret = []
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
                    column_start = line_start + len(search2)
                    column_end = content.find(search3, column_start)
                    element = content[column_start:column_end]
                    line_start = column_end
                    if len(elements)==0:
                        pass
                    elif len(elements)==1:
                        element = element.strip()
                    elements.append(element)
                else:
                    line_start = line_end
            if elements[2] != '' and elements[3] !='':
                ret.append(extract_job(elements))
            cur_pos = line_end
        else:
            cur_pos = len(content)

    return ret

def get_all_ingamejob_jobs():
    path = os.path.dirname(__file__)
    filename = path + "/ingamejobs_Submitted CVs.html"
    jobs = get_htlm_table_content(filename)

    return jobs


def main():

    jobs = get_all_ingamejob_jobs()

    return 0


if __name__ == "__main__":
    retval = main()

    print("exited with return code %s" % retval)
    exit(retval)
