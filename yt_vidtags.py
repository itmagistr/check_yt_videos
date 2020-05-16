# -*- coding: utf-8 -*-
import sys
import argparse
import time
import datetime
import pyperclip
from check_yt_models import *
from pony import orm
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import * #
import logging
logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(logging.FileHandler("info_yt_vidtags.log"))



def main(opts):
	urls={}
	with open(opts.infile, 'r') as fl:
		for line in fl.readlines():
			if 'youtube.com' in line:
				if line.strip()[-5:]=='/edit':
					vid = line.strip()[-16:-5]
				else:
					vid = line.strip()[-11:]
				urls[vid]='https://studio.youtube.com/video/{}/edit'.format(vid)
	urlslen = len(urls.keys())
	logging.info('Подготовлено {} видео для анализа'.format(urlslen))
	logging.info('Попытка подключиться к браузеру 127.0.0.1:9222 ...')
	chrome_options = Options()
	chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222") # запустить предварительно Хром
	driver = webdriver.Chrome(opts.webdriver, options=chrome_options)
	time.sleep(3)
	driver.set_page_load_timeout(120)
	driver.implicitly_wait(10)
	driver.maximize_window()
	discardChanges(driver,2) #если при запуске есть не сохраненные изменения, то отменяем перед началом перехода по ссылке
	#driver.get("http://ya.ru")
	
	if opts.words=='1':
		# собрать рейтинг seo для слов из файла для видео в первой строке
		rateWords(driver, opts)
	else:
		excludeTags = []
		if opts.update=='2':
			excludeTags = getExtags(1, 2, 7) # min< 1, avg< 2, max< 7
		crow=0
		for i, u in urls.items():
			crow+=1
			logging.info('-------- Обработка {:03d} из {:03d} ({:06.2f} %), {}'.format(crow, urlslen, 100.00*crow/urlslen, u))
			cdata = {}
			
			if opts.update == '3':
				# обновление тегов если значение рейтингов выше
				odt = datetime.datetime.strptime(opts.dt, '%Y-%m-%d %H:%M')
				d = CheckSavedData(i, odt)
				if d is not None:
					logging.info('treal:{} -> {}, tshow: {} -> {}, at {}'.format(d['rate'][0]['treal'], d['rate'][1]['treal'], d['rate'][0]['tshow'], d['rate'][1]['tshow'], d['dt']))
				else:
					tagsUpdate(driver, i, u, opts)

			elif opts.update in '012': #режим 0, 1, 2
				driver.get(u)
				time.sleep(2)
				try:
					testElm = WebDriverWait(driver, float(opts.timeout)).until(lambda x: x.find_element_by_class_name("stat-value-high-volume-ranked-tags"))
				except TimeoutException:
					logging.info("Превышено время ожидания загрузки страницы. Попытка обработать следующую ссылку.")
					continue
				
				if opts.update == '2':
						# для видео добавить теги, которые есть в БД, но не проверялись под данным видео
						for t in getDBtags(i, u, excludeTags):
							cdata[t]={}
				elif opts.update in '01': #режим 0 или 1
					#собрать теги
					for elm in driver.find_elements_by_xpath("//*[@id='child-input']//ytcp-chip[@role='button']"):
						text = elm.get_attribute('vidiq-keyword')
						if opts.update == '0':
							# все теги видео добавить к проверке
							cdata[text]={}
						elif opts.update == '1':
							if getDBTagSeo(i, u, text) < 0.01:
								# новые и с оценкой ноль добавить для проверки
								cdata[text]={}

				
				# добавить два слова для очистки тегов, чтобы гарантированно отображалась кнопка удалить все теги
				elq = driver.find_element_by_id('text-input')
				elq.click()
				
				# pyperclip.copy('word1, word2')
				# time.sleep(0.5)
				# elq.send_keys(Keys.CONTROL, 'v')
				# time.sleep(0.5)
				
				# #clear all tags
				doit_clear=2
				while doit_clear>0:
					try:
						di = driver.find_element_by_id('clear-button')
						di.click()
						doit_clear=0
					except:
						logging.info("find_element_by_id('clear-button') Unexpected error: {}".format(sys.exc_info()[0]))
						elq.send_keys('wr1,wr2', Keys.ENTER)
						time.sleep(0.5)
						doit_clear-=1

				# по тегам сохранить рейтинг
				tagscnt=1+len(cdata.keys())
				for t in cdata.keys():
					tagscnt-=1
					#add new tags
					elq.click()
					if opts.clipboard == '1':
						pyperclip.copy(t)
						time.sleep(0.5)
						#elq.send_keys(Keys.CONTROL, 'v')
						elq.send_keys(Keys.SHIFT, Keys.INSERT)
					else:
						elq.send_keys(t, Keys.ENTER)
					time.sleep(3)

					#get SEO score
					elm=driver.find_element_by_class_name('stat-value-seo-score')
					elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
					#logging.info('seo {}'.format(elm1.text))
					cdata[t]['seo'] = float(elm1.text)
					
					if cdata[t]['seo'] < 0.01:
						# если не успело значение обновиться, то подождем еще и вычитаем повторно
						time.sleep(2)
						#get SEO score
						elm=driver.find_element_by_class_name('stat-value-seo-score')
						elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
						#logging.info('seo2 {}'.format(elm1.text))
						cdata[t]['seo'] = float(elm1.text)
					getScores(driver, cdata[t])
					
					# удалить тег
					try:
						btn = driver.find_elements_by_xpath("//ytcp-icon-button[@id='delete-icon']")
						if len(btn) > 1:
							di = driver.find_element_by_id('clear-button')
							di.click()
						else:
							btn[0].click()
					except:
						logging.info("ERROR: {}".format(sys.exc_info()[0]))
						

					logging.info('{:03d}/{:03d}, {:03d} {}->{}'.format(crow, urlslen, tagscnt, t, cdata[t]['seo']))
					if opts.update=='2':
						saveindb({'vid': i, 'url': u, 'tags': {t: cdata[t]}, })
				
				#logging.info('cancel changes')
				btn=driver.find_element_by_id('discard')
				btn.click()
				time.sleep(0.5)

				if opts.update!='2':
					saveindb({'vid': i, 'url': u, 'tags': cdata})
			
		




def tagsUpdate(drv, vid, url, o):
	svd = 0 # не привело к сохранению в видео ютюб
	drv.get(url)
	time.sleep(2)
	try:
		testElm = WebDriverWait(drv, float(o.timeout)).until(lambda x: x.find_element_by_class_name("stat-value-high-volume-ranked-tags"))
	except TimeoutException:
		logging.info("Превышено время ожидания загрузки страницы. Попытка обработать следующую ссылку.")
		
	# сформировать предлагаемый перечень тегов для замены
	ntags=getSEOtags(vid)

	# сохранить текущее состояние видео
	vidSEO1 = getYTseo4Vid(drv)
	logging.info('seo1: {}'.format(vidSEO1['treal']))
	
	if len(ntags) > 0:
		logging.info('{} слов для формирования строки тегов'.format(len(ntags)))
		# подставить новую строку тегов
		tagStr = ''
		tagslen = 0
		for t in ntags:
			if tagslen < 500 and tagslen+len(t) < 500:
				tagStr += ','+t
				tagslen +=  len(t)
			else:
				break
		
		#logging.info('new tags:'+tagStr)

		inp = drv.find_element_by_id('text-input')
		clearAlltags(drv, inp)
		inp.click()
		pyperclip.copy(tagStr)
		time.sleep(0.5)
		# вставить новую строку тегов
		#inp.send_keys(Keys.CONTROL, 'v')
		inp.send_keys(Keys.SHIFT, Keys.INSERT)
		time.sleep(2)
		# проверить длинну <div slot="description" id="tags-count" class="style-scope ytcp-video-metadata-basics">155/500</div>
		tlen = 501
		while tlen > 500:
			# откорректировать длинну
			tagslength = drv.find_element_by_id('tags-count')
			#logging.info('tags-count: {}'.format(tagslength.text))
			chcnt = tagslength.text.split('/')
			#logging.info('tags-count: {}'.format(chcnt[0]))
			tlen = int(chcnt[0])
			if tlen > 500:
				delbtns = drv.find_elements_by_xpath("//ytcp-icon-button[@id='delete-icon']")
				if len(delbtns) > 0:
					delbtns[-1].click()
	else:
		logging.info('Нет слов для формирования строки тегов. Работаем с текущими')
		# вставлять нечего, далее работаем с тем, что есть

	# получить текущее состояние видео
	time.sleep(1)
	vidSEO2 = getYTseo4Vid(drv)
	logging.info('seo2: {}'.format(vidSEO2['treal']))
	
	#если рейтинг выше, то сохранить
	if vidSEO2['treal'] > vidSEO1['treal'] and (vidSEO1['tshow']<0.1 or vidSEO2['tshow'] > vidSEO1['tshow']):
		logging.info('!!! {:05.2f} > {:05.2f} SAVE'.format(float(vidSEO2['treal']), float(vidSEO1['treal'])))
		# save this
		svd = 1
		elms=drv.find_elements_by_xpath("//ytcp-button[@id='save']") #driver.find_element_by_id('save')
		if len(elms)>0:
			elms[0].click()
			time.sleep(0.5)
	
	# продолжаем улучшать, пробуем удалять по одному тегу, возможно найдем более высокое значение рейтинга
	todo = True
	fup = 0
	fdown = 0
	iteration = 0
	vidSEOlast = vidSEO2.copy()
	while todo and iteration < 100 and fdown < 1 and fup < 2:
		iteration+=1
		tlen = readTagsLen(drv)
		if tlen > 0:
			#пытаемся удалить последний тег
			delbtns = drv.find_elements_by_xpath("//ytcp-icon-button[@id='delete-icon']")
			if len(delbtns) > 0:
				parentelm = delbtns[-1].find_element_by_xpath("./..")
				logging.info('удаляем тег: {}'.format(parentelm.get_attribute('vidiq-keyword')))
				delbtns[-1].click()
				time.sleep(2)

		vidSEOcur = getYTseo4Vid(drv)

		if ( vidSEOlast['treal'] > vidSEOcur['treal'] ): #and ( abs(vidSEOlast['tshow'] - vidSEOcur['tshow']) <0.1 ):
			# уменьшился рейтинг после удаления тега - отменяем и завершаем подбор
			fdown +=1
			logging.info('--- {:05.2f} < {:05.2f} DISCARD'.format(float(vidSEOcur['treal']), float(vidSEOlast['treal'])))
			vidSEOlast = vidSEOcur.copy()

		elif ( vidSEOlast['treal'] < vidSEOcur['treal'] ):
			# сохранить и продолжить удалять до следующего изменения
			svd = 1
			fup +=1
			logging.info('!!! {:05.2f} > {:05.2f} SAVE {}'.format(float(vidSEOcur['treal']), float(vidSEOlast['treal']), fup))
			elms=drv.find_elements_by_xpath("//ytcp-button[@id='save']") #driver.find_element_by_id('save')
			if len(elms)>0:
				elms[0].click()
				time.sleep(0.5)
			vidSEOlast = vidSEOcur.copy()

	if fdown > 0:
		# cancel
		#logging.info(' :( discard, seo2 {:05.2f} =< {:05.2f} seo1.'.format(float(vidSEO2['treal']), float(vidSEO1['treal'])))
		btn=drv.find_element_by_id('discard')
		btn.click()
		

	# сохранить рейтинг в БД
	time.sleep(3)
	vidSEO2 = getYTseo4Vid(drv)
	if float(vidSEO2['treal']) > float(vidSEO1['treal']):
		logging.info('!!! текущий seo: {:05.2f} > старого {:05.2f}'.format(float(vidSEO2['treal']), float(vidSEO1['treal'])))
	elif float(vidSEO2['treal']) <= float(vidSEO1['treal']):
		logging.info('текущий seo: {:05.2f} == старому {:05.2f}'.format(float(vidSEO2['treal']), float(vidSEO1['treal'])))
	
	saveSEOupdate(vid, [vidSEO1, vidSEO2], svd)

def readTagsLen(drv):
	tagslength = drv.find_element_by_id('tags-count')
	chcnt = tagslength.text.split('/')
	return int(chcnt[0])

def readTagsCnt(drv):
	return len(drv.find_elements_by_xpath("//ytcp-icon-button[@id='delete-icon']"))

def clearAlltags(drv, inp):
	# clear all tags
	# inp = drv.find_element_by_id('text-input')
	inp.click()
	time.sleep(0.5)
	doit_clear=2
	while doit_clear>0:
		try:
			di = drv.find_element_by_id('clear-button')
			di.click()
			doit_clear=0
		except:
			logging.info("find_element_by_id('clear-button') Unexpected error: {}".format(sys.exc_info()[0]))
			inp.send_keys('wr1,wr2', Keys.ENTER)
			time.sleep(0.5)
			doit_clear-=1
	pass

# удалить тег
def delTag(drv):
	try:
		btn = drv.find_elements_by_xpath("//ytcp-icon-button[@id='delete-icon']")
		if len(btn) > 1:
			di = drv.find_element_by_id('clear-button')
			di.click()
		else:
			btn[0].click()
	except:
		logging.info("ERROR: {}".format(sys.exc_info()[0]))


def saveindb(vdata):
	with orm.db_session:
		for t, d in vdata['tags'].items():
			dd = {'vid': vdata['vid'], 'url': vdata['url'], 'tag': t, 'seo': d['seo'], 'real': d['real'], 'tcount': d['tcount'], 'tpopular': d['tpopular'],
				  'tintitle': d['tintitle'], 'tindesc': d['tindesc'], 'triple': d['triple'], 'tshow': d['tshow'], 'ranked': d['ranked'], 'hivolume': d['hivolume']}
			
			ts = TagSEO.get(vid=vdata['vid'], url=vdata['url'], tag=t)
			if ts is not None:
				ts.dt=datetime.datetime.now()
				ts.seo = d['seo']
				ts.real = d['real']
				ts.tcount = d['tcount']
				ts.tpopular = d['tpopular']
				ts.tintitle = d['tintitle']
				ts.tindesc = d['tindesc']
				ts.triple = d['triple']
				ts.tshow = d['tshow']
				ts.ranked = d['ranked']
				ts.hivolume = d['hivolume']
				ts.data = dd
			else:
				ts = TagSEO(vid=vdata['vid'], url=vdata['url'], tag=t, seo=d['seo'],
					real=d['real'], tcount=d['tcount'], tpopular=d['tpopular'], tintitle=d['tintitle'], tindesc=d['tindesc'],
					triple=d['triple'], tshow=d['tshow'], ranked=d['ranked'], hivolume=d['hivolume'], data=dd)

def saveSEOupdate(vid, vdata, saved):
	with orm.db_session:
		if len(vdata)==2:
			TagUpdate(vid=vid, tags1=','.join(vdata[0]['tags']), real1=vdata[0]['treal'], tshow1=vdata[0]['tshow'], 
				tags2=','.join(vdata[1]['tags']), real2=vdata[1]['treal'], tshow2=vdata[1]['tshow'], jdata=vdata, saved=saved)
		else:
			logging.info('Error: vdata has to 2 elements!!!')
	pass

def getSEOtags(vid):
	tgs=[]
	with orm.db_session:
		for tg in TagSEO.select(lambda t: t.vid==vid).order_by(orm.desc(TagSEO.seo)):
			#if tg.tag not in tgs:
			tgs+=[tg.tag]
	return tgs

def getDBTagSeo(vid, url, tag):
	resseo = 0
	with orm.db_session:
		ts = TagSEO.get(vid=vid, url=url, tag=tag)
		if ts is not None:
			resseo = ts.seo
	return resseo

def getExtags(minV, avgV, maxV):
	etags = []
	with orm.db_session:
		cnttags = orm.select(t.tag for t in TagSEO).count()
		etags = [tg for tg in orm.select(t.tag for t in TagSEO if orm.min(t.seo) < minV and orm.avg(t.seo) < avgV and orm.max(t.seo) < maxV)]
		logging.info('список слов исключений: {}/{}({:05.2f}%) шт. {}'.format(len(etags), cnttags, float(len(etags)*100.0/cnttags), etags))
	return etags

def getDBtags(vid, url, extags=[]):
	restags = []
	with orm.db_session:
		# теги видео
		tags=[t.tag for t in TagSEO.select(lambda t: t.url==url and t.vid==vid)]
		# теги исключения
		# extags
		if extags is None:
			extags = []
		#logging.info(tags)
		for tss in TagSEO.select(lambda ts: ts.vid!=vid and ts.url!=url and ts.tag not in tags and ts.tag not in extags).order_by(orm.desc(TagSEO.seo)):
			restags+=[tss.tag]
		#logging.info(restags)
	return restags

def getScores(dr, tdata):
	#get h1 stat-value-undefined two times
	elms=dr.find_elements_by_class_name('stat-value-undefined')
	elm1 = elms[0].find_elements_by_xpath(".//span[@class='value-inner']")[0]
	tdata['real'] = float(elm1.text)

	elm1 = elms[1].find_elements_by_xpath(".//span[@class='value-inner']")[0]
	tdata['tshow'] = float(elm1.text)

	#get stat-value-tag-count
	elm=dr.find_element_by_class_name('stat-value-tag-count')
	elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
	tdata['tcount'] = int(elm1.text)

	#get stat-value-tag-volume
	elm=dr.find_element_by_class_name('stat-value-tag-volume')
	elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
	tdata['tpopular'] = int(elm1.text)

	#get stat-value-keywords-in-title
	elm=dr.find_element_by_class_name('stat-value-keywords-in-title')
	elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
	tdata['tintitle'] = int(elm1.text)

	#get stat-value-keywords-in-description
	try:
		elm=dr.find_element_by_class_name('stat-value-keywords-in-description')
		elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
		tdata['tindesc'] = int(elm1.text)
	except:
		logging.info("stat-value-keywords-in-description Unexpected error: {}".format(sys.exc_info()[0]))

	#get stat-value-tripled-keywords
	try:
		elm=dr.find_element_by_class_name('stat-value-tripled-keywords')
		elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
		tdata['triple'] = int(elm1.text)
	except:
		logging.info("stat-value-tripled-keywords Unexpected error: {}".format(sys.exc_info()[0]))

				
	#get <span class="stat-value stat-value-ranked-tags"><span class="value-inner">0</span><span class="out-of">/5</span></span>
	try:
		elm=dr.find_element_by_class_name('stat-value-ranked-tags')
		elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
		tdata['ranked'] = int(elm1.text)
	except:
		logging.info("stat-value-ranked-tags Unexpected error: {}".format(sys.exc_info()[0]))

	#get <span class="stat-value stat-value-high-volume-ranked-tags"><span class="value-inner">0</span><span class="out-of">/5</span></span>
	try:
		elm=dr.find_element_by_class_name('stat-value-high-volume-ranked-tags')
		elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
		tdata['hivolume'] = int(elm1.text)
	except:
		logging.info("stat-value-high-volume-ranked-tags Unexpected error: {}".format(sys.exc_info()[0]))

	pass

# --update=3 собрать теги и рейтинги
def getYTseo4Vid(drv):
	#собрать теги
	# inp = drv.find_element_by_id('text-input')
	# inp.click()
	# time.sleep(0.3)
	tags=[]
	for elm in drv.find_elements_by_xpath("//*[@id='child-input']//ytcp-chip[@role='button']"):
		text = elm.get_attribute('vidiq-keyword')
		tags+=[text]
	
	# собрать рейтинги
	elms=drv.find_elements_by_class_name('stat-value-undefined')
	elm1 = elms[0].find_elements_by_xpath(".//span[@class='value-inner']")[0]
	tr = float(elm1.text)

	elm1 = elms[1].find_elements_by_xpath(".//span[@class='value-inner']")[0]
	tsh = float(elm1.text)

	try:
		elm=drv.find_element_by_class_name('stat-value-ranked-tags')
		elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
		tranked = int(elm1.text)
	except:
		logging.info("stat-value-ranked-tags Unexpected error: {}".format(sys.exc_info()[0]))

	#get <span class="stat-value stat-value-high-volume-ranked-tags"><span class="value-inner">0</span><span class="out-of">/5</span></span>
	try:
		elm=drv.find_element_by_class_name('stat-value-high-volume-ranked-tags')
		elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
		thivolume = int(elm1.text)
	except:
		logging.info("stat-value-high-volume-ranked-tags Unexpected error: {}".format(sys.exc_info()[0]))


	return {'tags': tags, 'treal': tr, 'tshow': tsh, 'tranked': tranked, 'thivolume': thivolume, }

def CheckSavedData(vid, dt):
	cdjson = None
	with orm.db_session:
		datas = TagUpdate.select(lambda t: t.vid==vid and  t.dt > dt and t.saved==1).order_by(orm.desc(TagUpdate.dt))
		for d in datas:
			cdjson={'dt': d.dt, 'rate': d.jdata, }
			break
	return cdjson

def discardChanges(drv, wt=0.5):
	#logging.info('cancel changes')
	try:
		btn=drv.find_element_by_id('discard')
		btn.click()
		time.sleep(wt)
	except:
		pass

def rateWords(drv, opts):
	words = []
	addwrds = []
	with open(opts.infile, 'r', encoding='utf-8') as fl:
		linecnt = 0
		for line in fl.readlines():
			linecnt+=1
			if linecnt==1:
				url = line.strip()
			else:
				t = line.strip()
				if len(t)>0:
					words+=[t]
	wordscnt= len(words)				
	logging.info('Прочитано из файла слов: {}'.format(wordscnt))
	logging.info('Перехожу по ссылке: {}'.format(url))
	#discardChanges(drv,1)
	drv.get(url)
	time.sleep(3)
	try:
		testElm = WebDriverWait(drv, float(opts.timeout)).until(lambda x: x.find_element_by_class_name("stat-value-high-volume-ranked-tags"))
	except TimeoutException:
		logging.info("Превышено время ожидания загрузки страницы.")
		exit(11)
		
	inp = drv.find_element_by_id('text-input')
	clearAlltags(drv, inp)
	inp.click()
	curw=0
	for w in words:
		curw+=1
		inp.click()
		if opts.clipboard=='1':
			pyperclip.copy(w)
			time.sleep(0.5)
			inp.send_keys(Keys.SHIFT, Keys.INSERT)
		else:
			inp.send_keys(w+',',Keys.ENTER)
		time.sleep(3)
		# подождать появления подсказок
		sugText=''
		try:
			wElm = WebDriverWait(drv, float(2)).until(lambda x: x.find_element_by_class_name("vidiq-studio-beta-keyword-text"))
			sugText=wElm.text
		except TimeoutException:
			pass
		if len(sugText)>0:
			restxt = []
			for el in drv.find_elements_by_class_name("vidiq-studio-beta-keyword-text"):
				if el.is_displayed():
					restxt += [el.text]
			if len(restxt) > 0:
				sugText=';'.join(restxt)
				addwrds+=restxt

		#get SEO score
		elm=drv.find_element_by_class_name('stat-value-seo-score')
		elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
		logging.info('{:03d}/{:03d} ;{:05.2f};{};{}'.format(curw, wordscnt, float(elm1.text), w, sugText))
		delTag(drv)
	discardChanges(drv)
	newresfile = '!addwords_{}.txt'.format(datetime.datetime.now().strftime('%y%m%d_%H%M'))
	with open(newresfile, 'w', encoding='utf-8') as flres:
		for adw in addwrds:
			flres.writelines([adw+'\n'])
	exit(999)

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--timeout', help='waiting timeout to load the page', default='10')
	parser.add_argument('--infile', help='input file xlsm', default='listurls.txt')
	parser.add_argument('--webdriver', help='web driver path', default='C:\\bin\\webdriver\\chromedriver')
	parser.add_argument('--update', help='update new and zero tags', default='0')
	# 0- сбор тегов для входных видео; 1-новые и с оценкой ноль теги добавить для проверки; 2-проверка тегов из других видео на seo под анализируемым видео
	parser.add_argument('--clipboard', help='inserts tags by clipboard', default='1')
	
	parser.add_argument('--dt', help='expire datetime', default='2020-05-12 12:00')
	parser.add_argument('--words', help='rate words on seo in infile', default='0')
	args = parser.parse_args()
	main(args)

	# cmd line yt_vidtags.exe --timeout=12 --webdriver="C:\Windows\chromedriver.exe" --infile="!in.txt"