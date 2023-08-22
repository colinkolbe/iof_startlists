import math
import shutil
import os.path
import requests
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.firefox.options import Options

# main function
def getStartLists(eventId, wreDate, sprintWRE, firstBibNumber, firstStart, 
                  startInterval, amountLongerStartInterval, timeGap, eventSpecificFunction,
                  qualificationRace, randomSeed, bestRankedFirst, startingGroups, eventSpecificArgs):
    fnM = 'wrs_M_{0}_{1}_{2}.csv'.format(wreDate[0], wreDate[1], wreDate[2])
    fnW = 'wrs_W_{0}_{1}_{2}.csv'.format(wreDate[0], wreDate[1], wreDate[2])
    getWreData([fnM, fnW], sprintWRE, wreDate)
    wrsM, wrsW = pd.read_csv(fnM), pd.read_csv(fnW)
    
    if startingGroups:
        entriesM, entriesW = pd.read_csv('entriesM.csv'), pd.read_csv('entriesW.csv')
    else: 
        entriesM, entriesW = getEntryData(eventId)

    startListM = createStartLists(wrsM, entriesM, firstBibNumber[0], firstStart[0], 
                                startInterval[0], amountLongerStartInterval[0], timeGap[0],
                                eventSpecificFunction[0], qualificationRace, bestRankedFirst,
                                startingGroups, randomSeed, eventSpecificArgs[0])
    startListW = createStartLists(wrsW, entriesW, firstBibNumber[1], firstStart[1],
                                startInterval[1], amountLongerStartInterval[1], timeGap[1],
                                eventSpecificFunction[1], qualificationRace, bestRankedFirst,
                                startingGroups, randomSeed, eventSpecificArgs[1])

    saveToXlsx(startListM, startListW, eventId, qualificationRace, startingGroups, True)

    return (startListM, startListW)


# actual startlist creation
# mainly four cases: eventSpecific, startingGroups (early, middle, late), 
# qualificationRace or purely based on WRS
def createStartLists(wrs, entries, firstBibNumber, firstStart, startInt, 
                     amountLongerStartInterval, timeGap, eventSpecificFunction,
                     qualificationRace, bestRankedFirst, startingGroups, randomSeed,
                     eventSpecificArgs):
    entries = entries.loc[:,('Punching card number', 'Name', 'Organisation')]
    entries.loc[:, 'Punching card number'] = pd.to_numeric(entries.loc[:, 'Punching card number'], downcast='integer')
    entries.insert(0, 'WRS', entries.loc[:,'Name'].apply(lambda x: 0 if x not in wrs.Name.values 
                                            else wrs.loc[wrs['Name'] == x, 'WRS points'].iloc[0]))
    entries.sort_values(by=['WRS'], ascending=False, ignore_index=True, inplace=True)
    
    if eventSpecificFunction != None:
        entries = eventSpecificFunction(entries, firstBibNumber, firstStart, startInt, 
                     amountLongerStartInterval, timeGap, qualificationRace, bestRankedFirst,
                    startingGroups, randomSeed, eventSpecificArgs)
        entries = rule_12_7(entries)
    else:
        if startingGroups: 
            groups = [None, None, None]
            for idx, group in enumerate(groups):
                group = entries.loc[entries.StartingGroups == idx + 1] # +1 because of input specification
                group = group.sample(n=len(group), random_state=randomSeed)
                group = rule_12_7(group)
                if idx > 0:
                    firstStart += len(group.index) * startInt
                startTimes = getStartTimes(len(group.index), firstStart , startInt, amountLongerStartInterval, timeGap)
                groups[idx] = group.insert(len(group.columns), 'Start time', startTimes)            
            entries = pd.concat(groups, ignore_index=True)
        elif qualificationRace: 
            # evenly distributing runners to the heats, best ranked runner is always in heat1
            heats = []
            for i in range(0, len(entries)):
                heats.append(i % 3)
            entries.insert(0, 'Heat', heats)

            heats = [None, None, None]
            for idx, heat in enumerate(heats):
                heat = entries.loc[entries.Heat == idx]
                heat = heat.sample(n=len(heat), random_state=randomSeed)
                heat = rule_12_7(heat)
                startTimes = getStartTimes(len(heat.index), firstStart, startInt, amountLongerStartInterval, timeGap)
                heats[idx] = heat.insert(len(heat.columns), 'Start time', startTimes)
            entries = heats
        else:
            entries = rule_12_7(entries)
            if bestRankedFirst == False: 
                tmp = entries.index
                entries = entries.iloc[::-1]
                entries.index = tmp

            startTimes = getStartTimes(len(entries), firstStart, startInt, amountLongerStartInterval, timeGap)
            entries.insert(len(entries.columns), 'Start time', startTimes)
        
        entries.insert(0, 'Bib number', (entries.index + firstBibNumber))

    return entries


# IOF Competition Rule 12.7
#   - Always start the draw with the best ranked runner first if not drawn randomly
def rule_12_7(entries):
    # Forward iteration because entries is sorted descending on WRS otherwise also correct
    for i in range(0, len(entries) - 2):
        if entries.loc[i].Organisation == entries.loc[i+1].Organisation:
            j = i+2
            while entries.loc[i+1].Organisation == entries.loc[j].Organisation:
                j += 1
            if j > (len(entries) - 2):
                i = len(entries)
                print('Possible problem in applying rule 12.7 in forward iteration.')
            else:
                n = j
                for k in range((j - (i+1) - 1), -1, -1):
                    # exectues multiple cascading swaps if needed
                    entries = swapDfRows(entries, i+1 + k, n)
                    n -= 1
    # Backward iteration because to ensure that not just the last two starters are not from
    # the nation but also no new issues result of that possible swap
    # See case: ..ABABB -> ..ABBAB -> ..BABAB
    for i in range(len(entries) - 1, 0, -1):
        if entries.loc[i].Organisation == entries.loc[i-1].Organisation:
            j = i-2
            while entries.loc[i-1].Organisation == entries.loc[j].Organisation:
                j -= 1
            if j < 0:
                i = 0
                print('Possible problem in applying rule 12.7 in backward iteration.')
            else: 
                n = j
                for k in range(((i-1) - j - 1), -1, -1):
                    # exectues multiple cascading swaps if needed
                    entries = swapDfRows(entries, n, i-1 - k)
                    n += 1

    return entries


# swaps two given df.rows based on their indices
def swapDfRows(df, oldIdx, newIdx):
    tmp = df.iloc[oldIdx].copy()
    df.iloc[oldIdx] = df.iloc[newIdx].copy()
    df.iloc[newIdx] = tmp
    return df


# @firstStart: [hh, mm, ss], @startInterval: [mm, ss]
def getStartTimes(countRunners, firstStart, startInt, amountLongerStartInterval, timeGap):
    mmInt, ssInt = startInt[0]
    startInterval = 60 * mmInt + ssInt
    currStartTime = 3600 * firstStart[0] + 60 * (firstStart[1] - mmInt) + (firstStart[2] - ssInt)
    longFormat = True
    if firstStart[2] == 0 and ssInt == 0 and startInt[1][1] == 0:
        longFormat = False
    startTimes = []
    for i in range(0, countRunners):
        if i >= (countRunners - amountLongerStartInterval): 
            mmInt, ssInt = startInt[1]
            startInterval = 60 * mmInt + ssInt
            currStartTime += 3600 * timeGap[0] + 60 * timeGap[1] + timeGap[2]
            amountLongerStartInterval = 0 # to only execute block once
        currStartTime += startInterval

        startTimes.append(secondsToString(currStartTime, longFormat))

    return startTimes


# replaces runners in startlist 
def replaceRunners(startListM, startListW, replaceRunners, eventId, qualificationRace, startingGroups):
    for idx, startlist in enumerate([startListM, startListW]):
        if qualificationRace:
            for heat in startListM:
                for tup in replaceRunners[idx]:
                    oldR, newR, newCard, newBib, newTime = tup
                    heat = replace(heat, oldR, newR, newCard, newBib, newTime)
        else: 
            for tup in replaceRunners[idx]:
                oldR, newR, newCard, newBib, newTime = tup
                startlist = replace(startlist, oldR, newR, newCard, newBib, newTime)

    saveToXlsx(startListM, startListW, eventId, qualificationRace, startingGroups, False)

    return startListM, startListW


# moves oldRunner to top of startlist and changes name and cardNumber
def replace(startList, oldRunner, newRunner, newPunchingCardNumber, newBibNumber, newStartTime):
    index = startList.loc[startList['Name'] == oldRunner].index
    if len(index) == 1:
        index = index.values.astype(int)[0]
        row = startList.iloc[index].copy()
        row['Name'] = newRunner
        row['Punching card number'] = newPunchingCardNumber
        row['Bib number'] = newBibNumber
        row['Start time'] = newStartTime
        startList.drop(index, inplace=True)
        startList.loc[-1] = row
        startList.index += 1
        startList.sort_index(inplace=True) 
        startList.reset_index(drop=True, inplace=True)

    return startList


# download html table and convert to dataframe
def getTableAsDf(url):
    headers = {'Accept-Language': 'en'}
    res = requests.get(url, headers=headers)
    assert res.ok 
    soup = BeautifulSoup(res.text, 'html.parser')

    tables = soup.find_all("table")
    tableM = tables[0].find_all("tr")[1:]
    tableW = tables[1].find_all("tr")[1:]

    columnNames = []
    for items in tables[0].find("tr"): 
        try:
            if items.get_text() != '\n':
                columnNames.append(items.get_text())
        except:
            continue

    dfs, tables, onlyOnce = (), [tableM, tableW], True
    for table in tables:
        data = []
        for element in table: 
            sub_data = []
            for sub_element in element:
                try:
                    if sub_element.get_text() != '\n':
                        sub_data.append(sub_element.get_text())
                except:
                    continue
            data.append(sub_data)
        if len(columnNames) == (len(data[0]) + 1) and onlyOnce:
            columnNames = columnNames[:-1]
            onlyOnce = False
            df = pd.DataFrame(data=data, columns=columnNames)
        else: 
            df = pd.DataFrame(data=data, columns=columnNames)
            if onlyOnce == True:
                df.drop(' ', axis=1, inplace=True)
        dfs += (df,)
    
    return dfs


# download WRE data from eventor
def getWreData(fileNames, sprintWRE, wreDate): 
    # discipline = ['FootO Middle/Long', 'FootO Sprint', 'MTBO', 'Ski-O', 'Trail-O'][discipline_idx] 
    discipline = 'FootO Middle/Long' if sprintWRE == False else 'FootO Sprint'
    for idx, fname in enumerate(fileNames):
        if os.path.isfile(fname) is False: 
            dir_path = os.path.dirname(os.path.realpath(__file__))
            # set options
            options = Options()
            options.set_preference("browser.download.folderList", 2)
            options.set_preference("browser.download.dir", dir_path)
            options.set_preference("browser.download.manager.showWhenStarting", False)
            options.set_preference("browser.helperApps.neverAsk.saveToDisk", 'text/csv')
            # options.add_argument('--headless') # might block Firefox for normal usage until restart of OS

            driver = webdriver.Firefox(options=options)
            driver.get("https://ranking.orienteering.org/Ranking")
            # set args 
            _select = Select(driver.find_element_by_id('MainContent_tbDateNew_ddlDay'))
            _select.select_by_visible_text(wreDate[0])
            _select = Select(driver.find_element_by_id('MainContent_tbDateNew_ddlMonth'))
            _select.select_by_visible_text(wreDate[1])
            _select = Select(driver.find_element_by_id('MainContent_tbDateNew_ddlYear'))
            _select.select_by_visible_text(wreDate[2])
            _select = Select(driver.find_element_by_id('MainContent_ddlSelectDiscipline'))
            _select.select_by_visible_text(discipline)
            if idx == 1:
                gender_select = Select(driver.find_element_by_id('MainContent_ddlGroup'))
                gender_select.select_by_visible_text('Women')

            # click buttons
            buttons = driver.find_elements(By.TAG_NAME, 'button')
            dropDownBtn = None
            for btn in buttons:
                if btn.text == 'Download':
                    dropDownBtn = btn
            assert dropDownBtn != None
            dropDownBtn.click()
            dropDownMenu = driver.find_element(By.CLASS_NAME, 'dropdown-menu')
            listItems = dropDownMenu.find_elements(By.TAG_NAME, 'li')
            downloadBtn = listItems[2]
            downloadBtn.click()
            driver.close()

            # rename downloaded file
            for f in os.listdir(dir_path):
                if 'iof_ranking' in f:
                    filename = f
            shutil.move(filename, os.path.join(dir_path,fname))

            # add Name column
            df = pd.read_csv(fname, sep=';')
            if 'Name' not in df.columns:
                df.insert(3, 'Name', df.apply(lambda x: x['First Name'] + ' ' + x['Last Name'], axis=1))
                df.to_csv(fname, mode='w+', index=False)
        else:
            print(fname,' already exists.')
        
        
# save startlist-dataframes to .xlsx
def saveToXlsx(startListM, startListW, eventId, qualificationRace, startingGroups, droppingColumns):
    fn = 'startlist_' + str(eventId) + '.xlsx'
    dropColumns = ['WRS']
    with pd.ExcelWriter(fn) as writer: 
         if qualificationRace:
            for i in range(0,3):
                dropColumns.append('Heat')
                dropColumns = dropColumns if droppingColumns else []
                startListM[i].drop(columns=dropColumns, inplace=True)
                startListW[i].drop(columns=dropColumns, inplace=True)
                startListM[i].to_excel(writer, sheet_name=('Men_Heat_' + str(i)), index=False)
                startListM[i].to_excel(writer, sheet_name=('Women_Heat_' + str(i)), index=False)
         else: 
            if startingGroups:
                dropColumns.append('StartingGroups')
            dropColumns = dropColumns if droppingColumns else []
            startListM.drop(columns=dropColumns, inplace=True)
            startListW.drop(columns=dropColumns, inplace=True)
            startListM.to_excel(writer, sheet_name='Startlist_Men', index=False)
            startListW.to_excel(writer, sheet_name='Startlist_Women', index=False)


# download entry data 
def getEntryData(eventId):
    entriesM, entriesW = getTableAsDf('https://eventor.orienteering.org/Events/Entries?eventId=' + str(eventId) + '&groupBy=EventClass')
    return (entriesM, entriesW)


# download start list of past event for proof of concept
def getOldStartList(eventId):
    startList_url = 'https://eventor.orienteering.org/Events/StartList?eventId=' + str(eventId) + '&groupBy=EventClass'
    startListM, startListW = getTableAsDf(startList_url)
    return (startListM, startListW)


# turns seconds into a string of format hh:mm:ss or hh:mm
# has leading zeros; does not handle seconds greater than one day
def secondsToString(seconds, longFormat):
    ss = seconds % 60
    hh = math.floor(seconds / 3600)
    mm = int((seconds - hh * 3600 - ss) / 60)

    ss = '0' + str(ss) if len(str(ss)) == 1 else ss
    mm = '0' + str(mm) if len(str(mm)) == 1 else mm
    hh = '0' + str(hh) if len(str(hh)) == 1 else hh
    s = '{0}:{1}'.format(str(hh), str(mm))
    if longFormat:
        s = s + ':' + str(ss)
    return s


########################################################################
# EXAMPLES of event-specific implementations
# Note that existing startlists of past events based on a random draw 
# can´t exactly be reproduced (unless method and seed are known)
# Similar can this lead to slight difference if two or more runners have the same WRS
# ESF := event specific function

# wrapper function with preset input values
def wc2_long_2023():
    eventId, wreDate = 7566, ['5', 'August', '2023'] 
    firstStart = [(8, 52, 0), (8, 57, 0)] 
    startInterval = [[(2, 0), (3, 0)], [(2, 0), (3, 0)]] 
    amountLongerStartInterval = [30, 30] 
    timeGap = [(0, 0, 0), (0, 0, 0)]
    eventSpecificFunction = [None, wc2_long_2023_ESF] 
    eventSpecificArgs = [(None, None), (70, 300)] # (amountSplit, timeBetweenGroups)
    bestRankedFirst, qualificationRace, startingGroups = False, False, False
    sprintWRE, randomSeed, firstBibNumber = False, None, [1, 201]
    startListM, startListW = getStartLists(eventId, wreDate, sprintWRE, firstBibNumber, firstStart, 
                                    startInterval, amountLongerStartInterval, timeGap, eventSpecificFunction, 
                                    qualificationRace, randomSeed, bestRankedFirst, startingGroups, eventSpecificArgs)

    return (startListM, startListW)

# ESF
def wc2_long_2023_ESF(entries, firstBibNumber, firstStart, startInt, amountLongerStartInterval, 
                  timeGap, qualificationRace, bestRankedFirst, startingGroups, randomSeed, 
                  eventSpecificArgs):
    amountSplit, timeBetweenGroups = eventSpecificArgs
    entries.sort_values(by=['WRS'], ascending=True, ignore_index=True, inplace=True)
    group1 = entries[(len(entries) - amountSplit):].copy()
    group2 = entries[:(len(entries) - amountSplit)].copy()

    startTimes = getStartTimes(len(group1), firstStart , startInt, amountLongerStartInterval, timeGap)
    group1.insert(len(group1.columns), 'Start time', startTimes)   
    
    hh, mm = startTimes[-1].split(':')
    secondStart = 3600 * int(hh) + 60 * int(mm) + timeBetweenGroups
    ss = secondStart % 60
    hh = math.floor(secondStart / 3600)
    mm = int((secondStart - hh * 3600 - ss) / 60)
    
    secondStart = (hh, mm, ss)
    startTimes = getStartTimes(len(group2), secondStart, startInt, 0, timeGap)
    group2.insert(len(group2.columns), 'Start time', startTimes)            
    
    entries = pd.concat([group1, group2], ignore_index=True)
    entries.insert(0, 'Bib number', (entries.index + firstBibNumber))

    return entries


# wrapper function with preset input values; no ESF needed
def wc2_sprint_2023():
    print('Note that the offical startlists did not comply with rule 12.7.')
    eventId, wreDate = 7563, ['1', 'August', '2023'] 
    firstStart = [(14, 23, 0), (14, 25, 0)] 
    startInterval = [[(1, 0), (1, 30)], [(1, 0), (1, 30)]] 
    amountLongerStartInterval = [40, 40] 
    timeGap = [(0, 2, 0), (1, 11, 0)]
    eventSpecificFunction = [None, None] 
    eventSpecificArgs = [(None), (None)]
    bestRankedFirst, qualificationRace, startingGroups = False, False, False
    sprintWRE, randomSeed, firstBibNumber = False, None, [1, 201]
    startListM, startListW = getStartLists(eventId, wreDate, sprintWRE, firstBibNumber, firstStart, 
                                    startInterval, amountLongerStartInterval, timeGap, eventSpecificFunction, 
                                    qualificationRace, randomSeed, bestRankedFirst, startingGroups, eventSpecificArgs)

    replaceMaleRunners = [('Soren Thrane Odum', 'Asbjorn Kaltoft', 8626196, 149, '14:24:00'),
                          ('Emil Svensk', 'Anton Johansson', 8140425, 150, '14:23:00')]
    toBeReplaced = [replaceMaleRunners, []]
    startListM, startListW = replaceRunners(startListM, startListW, toBeReplaced, eventId, qualificationRace, startingGroups)
    return startListM, startListW
