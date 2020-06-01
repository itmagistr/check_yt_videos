# -*- coding: utf-8 -*-
import os
import sys
import argparse
import time
import datetime
import openpyxl
import pyperclip
import googleapiclient.errors      #список ошибок доступа к YouTube Data API
import googleapiclient.discovery   #клиент доступа к YouTube Data API
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
logging.getLogger('googleapicliet.discovery_cache').setLevel(logging.CRITICAL)
logging.getLogger().addHandler(logging.FileHandler("info_yt_vidtags.log"))


def main(opts):
	
	if len(opts.chID) > 1:
		getVideoList(opts) # сформировать файл ссылок на видео канала
		return #выйти из выполнения

	urls=loadUrls(opts.infile)
	urlslen = len(urls.keys())
	logging.info('Подготовлено {} видео для анализа'.format(urlslen))
	
	driver = connect2Browser(opts)

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
			
def connect2Browser(opts):
	logging.info('Попытка подключиться к браузеру 127.0.0.1:9222 ...')
	chrome_options = Options()
	chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222") # запустить предварительно Хром
	drv = webdriver.Chrome(opts.webdriver, options=chrome_options)
	time.sleep(3)
	drv.set_page_load_timeout(120)
	drv.implicitly_wait(10)
	drv.maximize_window()
	discardChanges(drv,2) #если при запуске есть не сохраненные изменения, то отменяем перед началом перехода по ссылке
	#driver.get("http://ya.ru")
	tags_discardChanges(drv, 2)
	drv.get('https://youtube.com')
	try:
		testElm = WebDriverWait(drv, float(opts.timeout)).until(lambda x: x.find_element_by_id("avatar-btn"))
	except TimeoutException:
		logging.info("Выполните вход в аккаунт ютюб и перезапустите приложение.")
		exit(13)
	return drv

def loadUrls(flname):
	res = {}
	with open(flname, 'r') as fl:
		for line in fl.readlines():
			if 'youtube.com' in line:
				if line.strip()[-5:]=='/edit':
					vid = line.strip()[-16:-5]
				else:
					vid = line.strip()[-11:]
				res[vid]='https://studio.youtube.com/video/{}/edit'.format(vid)
	return res

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


def getVideoList(opts):
	# наименование сервиса Google
	api_service_name = "youtube"
	api_version = "v3"
	youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=opts.apiKey, cache_discovery=False)
	
	playlists=[]
	npage = 1
	tstr = ''
	# step 2 - получить список плейлистов
	######################################
	request = youtube.playlists().list(part="id", maxResults=10, channelId=opts.chID) 
	response = request.execute()
	playlists.extend(response["items"])
	
	while 'nextPageToken' in response and response["nextPageToken"]:
		request = youtube.playlists().list(part="id", maxResults=10, channelId=opts.chID, pageToken=response["nextPageToken"])
		response = request.execute()
		npage+=1
		playlists.extend(response["items"])
	#logging.info(playlists)
	
	plvideos = []
	for pl in playlists:
		npage = 1
		request = youtube.playlistItems().list(
			part="snippet", 
			maxResults=50,
			playlistId=pl["id"] # плейлист
		)
		response = request.execute()
		totalResults = response["pageInfo"]["totalResults"]
		
		#logging.info(response['items'])
		
		for itm in response["items"]:
			plvideos.extend([itm["snippet"]])
		
		while 'nextPageToken' in response:# and response["nextPageToken"] is not None:
			npToken = response.get('nextPageToken','not Found')
			
			request = youtube.playlistItems().list(
				part="snippet", # заменить на snippet 
				maxResults=50,
				pageToken=npToken,
				playlistId=pl["id"] # плейлист
			)
			response = request.execute()
			#logging.info(response['items'])
			for itm in response["items"]:
				plvideos.extend([itm["snippet"]]) # накапливаем список видео, обновляем характеристики видео, далее собираемтолько статистику
	#plvideos["channelId"]
	#plvideos["resourceId"]["videoId"]
	yturls=[]
	if len(opts.infile)>1:
		with open(opts.infile, 'r') as infl:
			for line in infl.readlines():
				if 'youtube.com' in line:
					yturls.append(line.strip())

	with open(getFilename(opts), 'w') as fl:
		# if opts.chvideos=='1':
		# 	for v in plvideos:
		# 		if v["channelId"] == opts.chID:
		# 			fl.writelines(['{};https://youtube.com/watch?v={}\n'.format(v["channelId"], v["resourceId"]["videoId"])])
		# else:
		if len(yturls) > 0:
			for v in plvideos:
				url = 'https://youtube.com/watch?v={}'.format(v["resourceId"]["videoId"])
				if url not in yturls:
					fl.writelines([url+'\n'])
		else:
			fl.writelines(['https://youtube.com/watch?v={}\n'.format(v["resourceId"]["videoId"]) for v in plvideos])

def getFilename(opts):
	res='{}_{}.txt'.format(opts.outflname, datetime.datetime.now().strftime('%y%m%d_%H%M'))
	return res

#------------------------------------- from check_yt_videos.py --------------------
def tags_openxls(flname):	
	logging.info(f'Чтение списка ссылок из файла {flname}')
	#logging.info(os.path.dirname(opts.xls))
	wb = openpyxl.load_workbook(filename=flname, read_only=False, keep_vba=True)
	if 'Обновление' in wb.sheetnames:
		wss = wb['Обновление']
	else:
		logging.info('source worksheet did not find')
		exit(2)
	if 'Статистика' in wb.sheetnames:
		wsd = wb['Статистика']
	else:
		logging.info('destination worksheet did not find')
		exit(3)
	# if 'Исключения' in wb.sheetnames:
	# 	wse = wb['Исключения']
	# else:
	# 	logging.info('exclusions worksheet did not find')
	if 'Теги' in wb.sheetnames:
		wst= wb['Теги']
	else:
		logging.info('tags worksheet did not find')

	newWBfile = '{}\\Ссылки_{}.xlsm'.format(os.path.dirname(flname), datetime.datetime.now().strftime('%y%m%d_%H%M'))
	logging.info(newWBfile)
	#return (wb, wss, wsd, wse, wst, newWBfile)
	return (wb, wss, wsd, wst, newWBfile)
	
	
	

def check_list(opts):
	started_at = time.monotonic()
	#if opts.tags == '0':  обновление статистики чек-листа
	#(wb, wss, wsd, wse, wst, newWBfile) = tags_openxls(opts.infile)
	(wb, wss, wsd, wst, newWBfile) = tags_openxls(opts.infile)

	urls = tags_getUrls(wss, opts.owner)
	urlslen = len(urls)
	logging.info(f'---------- Очередь для обработки {urlslen} ссылок')

	odt = datetime.datetime.strptime(opts.dt, '%Y-%m-%d %H:%M')
	logging.info('---- дата свежести сохранненых данных {}'.format(odt))
	if urlslen > 0:
		driver = connect2Browser(opts)
	crow=1
	for u in urls:
		logging.info('-------- Обработка {:03d} из {:03d} ({:05.2f} %), {}'.format(crow, urlslen, 100.00*crow/urlslen,u['title']))
		crow+=1

		svdata = tags_CheckSavedData(u['url'], odt)
		if svdata is not None and float(opts.seo) <= float(svdata["seo"]):
			# записать в эксель данные из БД
			tags_write2xls(wsd, crow, svdata)
		else:
			#запустить сбор данных и сохранение для дальнейшего использования
			if svdata is not None:
				logging.info('в БД seo = {}'.format(svdata["seo"]))
			else:
				logging.info('новое видео в списке, сбор информации')
			driver.get(u['url'])
			wsd.cell(row=crow, column=1, value=u['num'])
			wsd.cell(row=crow, column=2, value=u['title'])
			wsd.cell(row=crow, column=3, value=u['url'])
			time.sleep(1)
			# Обрабатывать ошибку "чужое видео" пример https://studio.youtube.com/video/ez5hxF1jP-A/edit
			try:
				myElem = WebDriverWait(driver, float(opts.timeout)).until(lambda x: x.find_element_by_class_name("stat-value-high-volume-ranked-tags"))
			except TimeoutException:
				if driver.find_element_by_id("error-image"):
					logging.info("Видео не доступно. {}, url={}".format(u['title'], u['url']))
					continue
				logging.info("Loading took too much time!")

			driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
			time.sleep(0.5)

			cdata={'num': u['num'],
				   'title': u['title'],
				   'url': u['url'],}

			#get SEO score
			elm=driver.find_element_by_class_name('stat-value-seo-score')
			elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
			logging.info('seo {}'.format(elm1.text))
			wsd.cell(row=crow, column=4, value=float(elm1.text))
			cdata['seo'] = elm1.text
			
			#get h1 stat-value-undefined two times
			elms=driver.find_elements_by_class_name('stat-value-undefined')
			#logging.info('elms count {}'.format(len(elms)))
			elm1 = elms[0].find_elements_by_xpath(".//span[@class='value-inner']")[0]
			#logging.info('undefined {}'.format(elm1.text))
			wsd.cell(row=crow, column=5, value=float(elm1.text))
			cdata['stat-value1'] = elm1.text

			elm1 = elms[1].find_elements_by_xpath(".//span[@class='value-inner']")[0]
			#logging.info('undefined {}'.format(elm1.text))
			wsd.cell(row=crow, column=11, value=int(elm1.text))
			cdata['stat-value2'] = elm1.text

			#get stat-value-tag-count
			elm=driver.find_element_by_class_name('stat-value-tag-count')
			elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
			#logging.info('count {}'.format(elm1.text))
			wsd.cell(row=crow, column=6, value=int(elm1.text))
			cdata['tag-count'] = elm1.text

			#get stat-value-tag-volume
			elm=driver.find_element_by_class_name('stat-value-tag-volume')
			elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
			#logging.info('volume {}'.format(elm1.text))
			wsd.cell(row=crow, column=7, value=int(elm1.text))
			cdata['tag-volume'] = elm1.text

			#get stat-value-keywords-in-title
			elm=driver.find_element_by_class_name('stat-value-keywords-in-title')
			elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
			#logging.info('title {}'.format(elm1.text))
			wsd.cell(row=crow, column=8, value=int(elm1.text))
			cdata['keywords-in-title'] = elm1.text

			#get stat-value-keywords-in-description
			try:
				elm=driver.find_element_by_class_name('stat-value-keywords-in-description')
				elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
				#logging.info('seo {}'.format(elm1.text))
				wsd.cell(row=crow, column=9, value=int(elm1.text))
				cdata['keywords-in-description'] = elm1.text
			except:
				logging.info("stat-value-keywords-in-description Unexpected error: {}".format(sys.exc_info()[0]))

			#get stat-value-tripled-keywords
			try:
				elm=driver.find_element_by_class_name('stat-value-tripled-keywords')
				elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
				#logging.info('tripled-keywords {}'.format(elm1.text))
				wsd.cell(row=crow, column=10, value=int(elm1.text))
				cdata['tripled-keywords'] = elm1.text
			except:
				logging.info("stat-value-tripled-keywords Unexpected error: {}".format(sys.exc_info()[0]))

			
			#get <span class="stat-value stat-value-ranked-tags"><span class="value-inner">0</span><span class="out-of">/5</span></span>
			try:
				elm=driver.find_element_by_class_name('stat-value-ranked-tags')
				elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
				#logging.info('undefined {}'.format(elm1.text))
				wsd.cell(row=crow, column=12, value=int(elm1.text))
				cdata['ranked-tags'] = elm1.text
			except:
				logging.info("stat-value-ranked-tags Unexpected error: {}".format(sys.exc_info()[0]))

			#get <span class="stat-value stat-value-high-volume-ranked-tags"><span class="value-inner">0</span><span class="out-of">/5</span></span>
			try:
				elm=driver.find_element_by_class_name('stat-value-high-volume-ranked-tags')
				elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
				#logging.info('undefined {}'.format(elm1.text))
				wsd.cell(row=crow, column=13, value=int(elm1.text))
				cdata['volume-ranked-tags'] = elm1.text
			except:
				logging.info("stat-value-high-volume-ranked-tags Unexpected error: {}".format(sys.exc_info()[0]))

			#get checklist
			try:
				driver.find_element_by_class_name('stat-box-checklist').click()
				elm=driver.find_element_by_class_name('stat-value-checklist')
				#logging.info(elm.get_attribute('innerHTML'))
				elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
				logging.info('check-list {}'.format(elm1.text))
				col=14
				wsd.cell(row=crow, column=col, value=int(elm1.text))
				cdata['chl-14'] = int(elm1.text)

				elm = driver.find_element_by_class_name('seo-checklist')
				for el in elm.find_elements_by_xpath(".//li")[:9]:
					col+=1
					wsd.cell(row=crow, column=col, value=1 if 'checked' == el.get_attribute('class') else 0)
					cdata['chl-{}'.format(col)] = 1 if 'checked' == el.get_attribute('class') else 0
			except:
				logging.info("stat-box-checklist Unexpected error: {}".format(sys.exc_info()[0]))

			tags_SaveCheckData(cdata)
		# except:
		# 	continue
	wb.save(newWBfile)
	logging.info(f'Результаты сохранены в файле {newWBfile}')
	logging.info('Работа сценария завершена за {:.3f} сек.'.format(time.monotonic() -started_at))
	return

def set_tags(opts):
	started_at = time.monotonic()
	#if opts.tags == '1': #подставляем теги
	(wb, wss, wsd, wse, wst, newWBfile) = tags_openxls(opts.infile)

	print('------------------tags')
	urltags = tags_getUrlsTags(wss, opts.owner, wst)
	print('------------------urls count ', len(urltags))
	#logging.info('key:{}, title:{}, tags:{}'.format(urltags[0]['key'], urltags[0]['title'], urltags[0]['tags']))
	crow=1
	urlslen = len(urltags)
	if urlslen > 0:
		driver = connect2Browser(opts)
	for u in urltags:
		logging.info('-------- Обработка {:03d} из {:03d} ({:06.2f} %), {}'.format(crow, urlslen, 100.00*crow/urlslen,u['title']))
		crow+=1

		svdata = None #CheckSavedData(u['url'], odt)
		if svdata is not None:
			# записать в эксель данные из БД
			#write2xls(wsd, crow, svdata)
			pass
		else:
			#запустить установку тегов
			driver.get(u['url'])
			time.sleep(1)
			# Обрабатывать ошибку "чужое видео" пример https://studio.youtube.com/video/ez5hxF1jP-A/edit
			try:
				myElem = WebDriverWait(driver, float(opts.timeout)).until(lambda x: x.find_element_by_class_name("stat-value-high-volume-ranked-tags"))
			except TimeoutException:
				if driver.find_element_by_id("error-image"):
					logging.info("Видео не доступно. {}, url={}".format(u['title'], u['url']))
					continue
				logging.info("Loading took too much time!")

			driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
			
			cdata={'num': u['num'],
				   'title': u['title'],
				   'url': u['url'],}

			#get SEO1 score
			elm=driver.find_element_by_class_name('stat-value-seo-score')
			elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
			logging.info('seo1 {}'.format(elm1.text))
			cdata['seo1'] = float(elm1.text)
			
			# Обновлять только если текущее значение seo меньше заданного граничного из эксель
			#logging.info('seo {} vs rate {}'.format(cdata['seo1'], float(u['taginfo']['maxseo'])))
			if cdata['seo1'] < float(u['taginfo']['maxseo']):

				elq = driver.find_element_by_id('text-input')
				elq.click()
				pyperclip.copy('word1, word2')
				time.sleep(0.5)
				elq.send_keys(Keys.SHIFT, Keys.INSERT)
				time.sleep(0.5)
				#clear all tags
				try:
					di = driver.find_element_by_id('clear-button')
					di.click()
				except:
					logging.info("find_element_by_id('clear-button') Unexpected error: {}".format(sys.exc_info()[0]))

				#add new tags
				elq.click()
				pyperclip.copy(u['taginfo']['newtags'])
				time.sleep(0.5)
				elq.send_keys(Keys.SHIFT, Keys.INSERT)
				time.sleep(3)

				#get SEO score
				elm=driver.find_element_by_class_name('stat-value-seo-score')
				elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
				logging.info('seo2 {}'.format(elm1.text))
				cdata['seo2'] = float(elm1.text)
				
				if cdata['seo2'] < 0.01:
					# если не успело значение обновиться, то подождем еще и вычитаем повторно
					time.sleep(2)
					#get SEO score
					elm=driver.find_element_by_class_name('stat-value-seo-score')
					elm1 = elm.find_elements_by_xpath(".//span[@class='value-inner']")[0]
					logging.info('seo2 {}'.format(elm1.text))
					cdata['seo2'] = float(elm1.text)

				if cdata['seo2'] > cdata['seo1']:
					# примем решение сохранить если значение увеличилось
					logging.info('save')
					elms=driver.find_elements_by_xpath("//ytcp-button[@id='save']") #driver.find_element_by_id('save')
					if len(elms)>0:
						elms[0].click()
						time.sleep(1)
				else:
					logging.info('cancel')
					elm=driver.find_element_by_id('discard')
					elm.click()
					time.sleep(0.5)
			else:
				logging.info('seo {} > tag rate {}'.format(cdata['seo1'], float(u['taginfo']['maxseo'])))	
			
			#exit(998) #удалить перед релизом, только для теста
	logging.info('Работа сценария завершена за {:.3f} сек.'.format(time.monotonic() - started_at))
	return

def tags_getUrls(ws, owner): #wse):
	#exurls = []
	urls=[]
	# doit = True
	# r = 1
	# emptyrows = 0
	# # сформировать список исключений
	# while doit:# and r < 3: #для анализа всего экселя требуется оставить только doit
	# 	r+=1
	# 	curval = wse.cell(row=r, column=6).value
	# 	if curval is not None:
	# 		if 'youtube.com' in curval:
	# 			exurls+=[curval]
	# 	else:
	# 		emptyrows+=1
	# 	if emptyrows > 3:
	# 		doit = False
	
	# прочитать ссылки на ютюб для сбора информации по чек-лист
	doit = True
	r = 1
	emptyrows = 0
	while doit:# and r < 3: #для анализа всего экселя требуется оставить только doit
		r+=1
		curval = ws.cell(row=r, column=6).value # link
		curown = ws.cell(row=r, column=4).value # owner
		if curval is not None:
			if ('youtube.com' in curval) and (curown == owner): #(not curval in exurls):
				url = curval.replace('https://youtube.com/watch?v=', 'https://studio.youtube.com/video/')+'/edit'
				logging.info(url)
				urls+=[{'url': url, 'num': ws.cell(row=r, column=1).value, 'title': ws.cell(row=r, column=5).value}]
		else:
			emptyrows+=1
		if emptyrows > 3:
			doit = False
	return urls

def tags_getUrlsTags(ws, owner, wst): #wse, 
	titlemask = {} # маски названий
	#exurls = [] # исключения
	urls=[] # видео

	# doit = True
	# r = 1
	# emptyrows = 0
	# # сформировать список исключений
	# while doit:# and r < 3: #для анализа всего экселя требуется оставить только doit
	# 	r+=1
	# 	curval = wse.cell(row=r, column=6).value
	# 	if curval is not None:
	# 		if 'youtube.com' in curval:
	# 			exurls+=[curval]
	# 	else:
	# 		emptyrows+=1
	# 	if emptyrows > 3:
	# 		doit = False
	
	
	doit = True
	r = 1
	emptyrows = 0
	# сформировать список масок названий
	while doit:# and r < 3: #для анализа всего экселя требуется оставить только doit
		r+=1
		curval = wst.cell(row=r, column=2).value
		if curval is not None:
			if '%' in curval:
				curkey = curval.replace('%', '')
				titlemask[curkey]={'newtags': wst.cell(row=r, column=4).value, 'maxseo': wst.cell(row=r, column=3).value, }
		else:
			emptyrows+=1
		if emptyrows > 3:
			doit = False
	#logging.info(titlemask.keys())
	# прочитать ссылки на ютюб для установки тегов
	doit = True
	r = 1
	emptyrows = 0
	while doit:# and r < 3: #для анализа всего экселя требуется оставить только doit
		r+=1
		curval = ws.cell(row=r, column=6).value
		title = ws.cell(row=r, column=5).value
		curown = ws.cell(row=r, column=4).value
		if curval is not None and title is not None:
			if ('youtube.com' in curval) and (curown == owner): # (not curval in exurls):
				for k in titlemask.keys():
					if k in title:
						url = curval.replace('https://youtube.com/watch?v=', 'https://studio.youtube.com/video/')+'/edit'
						logging.info(url)
						urls+=[{'url': url, 'num': ws.cell(row=r, column=1).value, 'title': ws.cell(row=r, column=5).value, 'key': k, 'taginfo': titlemask[k], }]
		else:
			emptyrows+=1
		if emptyrows > 3:
			doit = False

	return urls

def tags_CheckSavedData(url, dt):
	cdjson = None
	with orm.db_session:
		cd = CheckData.get(url=url)
		if cd is not None:
			if cd.dt > dt:
				cdjson = cd.data
	return cdjson

def tags_SaveCheckData(cdata):
	with orm.db_session:
		cd = CheckData.get(url=cdata['url'])
		if cd is None:
			cd = CheckData(url=cdata['url'], data=cdata)
		else:
			cd.data=cdata
			cd.dt=datetime.datetime.now()

def tags_write2xls(ws, crow, data):
	inum = ''
	if 'num' in data:
		if data["num"] is not None:
			inum = int(data["num"])
	ws.cell(row=crow, column=1, value=inum)
	ws.cell(row=crow, column=2, value=data["title"] if 'title' in data else '')
	ws.cell(row=crow, column=3, value=data["url"] if 'url' in data else '')

	ws.cell(row=crow, column=4, value=float(data["seo"]) if 'seo' in data else '')

	ws.cell(row=crow, column=5, value=float(data["stat-value1"]) if 'stat-value1' in data else '')
	ws.cell(row=crow, column=6, value=int(data["tag-count"]) if 'tag-count' in data else '')
	ws.cell(row=crow, column=7, value=int(data["tag-volume"]) if 'tag-volume' in data else '')
	ws.cell(row=crow, column=8, value=int(data["keywords-in-title"]) if 'keywords-in-title' in data else '')
	ws.cell(row=crow, column=9, value=int(data["keywords-in-description"]) if 'keywords-in-description' in data else '')
	ws.cell(row=crow, column=10, value=int(data["tripled-keywords"]) if 'tripled-keywords' in data else '')
	ws.cell(row=crow, column=11, value=int(data["stat-value2"]) if 'stat-value2' in data else '')
	ws.cell(row=crow, column=12, value=int(data["ranked-tags"]) if 'ranked-tags' in data else '')
	ws.cell(row=crow, column=13, value=int(data['volume-ranked-tags']) if 'volume-ranked-tags' in data else '')
	
	for i in range(14,24):
		key = 'chl-{}'.format(i)
		ws.cell(row=crow, column=i, value=int(data[key]) if key in data else '')

def tags_discardChanges(drv, wt=0.5):
	#logging.info('cancel changes')
	try:
		btn=drv.find_element_by_id('discard')
		btn.click()
		time.sleep(wt)
	except:
		pass

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--timeout', help='waiting timeout to load the page', default='10')
	parser.add_argument('--infile', help='input file xlsm', default='_')
	parser.add_argument('--webdriver', help='web driver path', default='C:\\bin\\webdriver\\chromedriver')
	parser.add_argument('--update', help='update new and zero tags', default='0')
	# 0- сбор тегов для входных видео; 1-новые и с оценкой ноль теги добавить для проверки; 2-проверка тегов из других видео на seo под анализируемым видео
	parser.add_argument('--clipboard', help='inserts tags by clipboard', default='1')
	
	parser.add_argument('--dt', help='expire datetime', default='2020-05-12 12:00')
	parser.add_argument('--words', help='rate words on seo in infile', default='0')
	
	parser.add_argument('--chID', help='channel ID', default='-')
	parser.add_argument('--chvideos', help='only channels videos', default='0')
	parser.add_argument('--outflname', help='part of the filename', default='chvideos')
	parser.add_argument('--apiKey', help='google api key', default='-')
	parser.add_argument('--tags', help='expire datetime', default='-')
	parser.add_argument('--seo',help='seo to process', default='50')
	parser.add_argument('--owner',help='owner of videos', default='Олег Брагинский')
	args = parser.parse_args()
	if args.tags:
		if args.tags == '0':
			check_list(args)
		elif args.tags == '1':
			set_tags(args)
	else:
		main(args)

	# cmd line yt_vidtags.exe --timeout=12 --webdriver="C:\Windows\chromedriver.exe" --infile="!in.txt"
