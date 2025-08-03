from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

if __name__ == '__main__':
    print("Hello")
    chrome_options = Options()
    
    
    # Здесь ваша строка, которая работала ранее
    # chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    
    # Создаём сервис с указанием пути к драйверу
    service = Service("c:\\bin\\Selenium\\chromedriver.exe")
    
    # Замените его, если он неверный.
    user_data_dir = "C:\\temp\\chrome_profile"
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")
    # user_data_dir = "C:\\Users\\itm\\AppData\\Local\\Google\\Chrome\\User Data"
    # chrome_options.add_argument(f"user-data-dir={user_data_dir}")
    # chrome_options.add_argument("--profile-directory=Profile Test")
    
    # --- строки для отключения GPU и sandbox ---
    # chrome_options.add_argument("--no-sandbox")
    # chrome_options.add_argument("--disable-gpu")
    # chrome_options.add_argument("--start-maximized")
    
    # Передаём сервис и опции в конструктор WebDriver
    # Обратите внимание, что service и options теперь являются именованными аргументами
    drv = webdriver.Chrome(service=service, options=chrome_options)
    
    drv.set_page_load_timeout(60)
    drv.implicitly_wait(10)
    drv.maximize_window()
    
    drv.get('https://www.youtube.com/feed/subscriptions')
    
    print("Press Enter to close the browser...")
    input()
    
# "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\itm\AppData\Local\Google\Chrome\User Data"
# "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome_profile"
   