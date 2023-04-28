from typing import List, Union
from bs4 import BeautifulSoup
from wattpad_scraper.models import Author, Book, Chapter, Status
from wattpad_scraper.utils.request import get, user_login
from wattpad_scraper.utils.log import Log
from urllib.parse import quote
import os
from wattpad_scraper.utils.reading_list import ReadingListRequest, ReadingList
from wattpad_scraper.utils.request import access_for_authenticated_user, User, session, clear_temp_dir


class Wattpad:
    """
    Wattpad class
    Attributes:
        verbose (bool): verbose mode
        timeout (int): timeout for requests
    
    Methods:
        login(username, password): login to Wattpad
        get_book_by_url(url): get book by url
        search_book(query): search book by query
        create_reading_list(name): create reading list
        create_reading_list_if_not_exists(name): create reading list if not exists
        get_user_reading_lists(): get user reading lists
        get_reading_list_by_name(name): get reading list by name
        add_to_reading_list(book, reading_list): add book to reading list
        remove_from_reading_list(book, reading_list): remove book from reading list
        delete_reading_list(reading_list): delete reading list    
    """
    def __init__(self, verbose=False, timeout=5, **kw) -> None:
        """
        Args:
            verbose (bool): verbose mode
            timeout (int): timeout for requests
        
        Keyword Args:
            max_workers (int): max workers for concurrent requests
            max_responses (int): max responses to store in memory
        """
        
        
        self.verbose = verbose
        os.environ["WATTPAD_VERBOSE"] = str(verbose)
        os.environ["WATTPAD_TIMEOUT"] = str(timeout)
        
        for key, value in kw.items():
            if key == "max_workers" or key == "workers":
                os.environ["WATTPAD_MAX_WORKERS"] = str(value)
            elif key == 'max_responses':
                os.environ['WATTPAD_MAX_RESPONSE'] = str(value)


        session.timeout = float(timeout)

        self.log = Log(name="wattpad_log", verbose=verbose)

        self.main_url = "https://www.wattpad.com"
        self.user: User = None  # type: ignore
        self.reading_list_req = ReadingListRequest(verbose=verbose)

    def clear_cache(self) -> bool:
        try:
            clear_temp_dir()
            return True
        except Exception as e:
            self.log.print(e, color="red")
            return False

    def login(self, username=None, password=None, cookie_file=None):
        """
        Login to Wattpad

        Args:
            username (string): username or email
            password (string): password
        """
        self.log.print("Logging in as {}".format(username), color="green")
        self.user = user_login(username, password, cookie_file)
        self.reading_list_req.user = self.user
        
        if 'USER_LOGGED_IN' in os.environ and os.environ['USER_LOGGED_IN'] == 'True':
            self.log.print("Logged in successfully", color="green")
            os.environ["WATTPAD_USERNAME"] = username # type: ignore
        else:
            self.log.print("Login failed", color="red")

    def get_book_by_url(self, url) -> Book:
        """
        Args:
            url (string): book url

        Returns:
            Book: returns a Book object

            Book object has the following attributes:
                url (string): book url
                name (string): book name
                author (Author): author object
                img_url (string): book image url
                tags (list): list of tags
                description (string): book description
                published (string): book published date
                reads (int): book reads
                votes (int): book votes
                status (Status): book status
                isMature (bool): book is mature
                chapters (list): list of chapter objects
        """

        response = get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        # Get book stats
        stats: [BeautifulSoup] = soup.find(class_='new-story-stats')  # type: ignore
        if stats is None:
            raise Exception("Book not found", url)

        lis = stats.find_all('li')

        reads = lis[0].find(
            class_="sr-only").get_text().replace('Reads', '').replace(',', '').strip()
        reads = int(reads)

        votes = lis[1].find(
            class_="sr-only").get_text().replace('Votes', '').replace(',', '').strip()
        votes = int(votes)

        parts = lis[2].find(
            class_="sr-only").get_text().replace('Parts', '').strip()
        parts = int(parts)

        # class : story-badges
        badges = soup.find(class_='story-badges')
        if badges is None:
            self.log.error("Badges not found", url)

        if badges:
            completed = badges.find(
                class_="tag-item").get_text().lower().startswith('com')  # type: ignore
            published = badges.find(
                class_='sr-only').get_text().split('First published ')[1]  # type: ignore
        else:
            completed = False
            published = None
        status = None
        if completed:
            status = Status.COMPLETED
        else:
            status = Status.ONGOING

        # is mature class mature
        mature = badges.find(class_="mature") is not None  # type: ignore

        # published sr-only > ex. Complete, First published Sep 25, 2018

        # description class description-text
        description = soup.find(class_='description-text')
        if description is None:
            self.log.error("Description not found", url)
            description = ""
        else:
            description = description.get_text().strip()

        # Get Chapters - Class: "story-chapter-list" > li > List<a> > text,href
        toc: [BeautifulSoup] = soup.find(class_='table-of-contents')  # type: ignore
        if toc is None:
            raise Exception("Table of Contents not found", url)

        lis = toc.find_all('li')
        chapters = []
        for n, li in enumerate(lis):
            a = li.find('a')
            url = a.get('href')
            if url.startswith('/'):
                url = self.main_url + url
            ch = Chapter(
                url=url, title=a.get_text().strip().replace('\n', ' '), chapter_number=n + 1)
            chapters.append(ch)

        # Get Title class: "sr-only" > text (title)
        title = soup.find(class_='sr-only')
        if title is None:
            self.log.error("Title not found", url)
            title = ""
        else:
            title = title.get_text().strip()

        # Get Author class: "author-info" > img,a > img:src,a:href,a:text
        author_info: BeautifulSoup = soup.find(
            class_='author-info')  # type: ignore

        imgurl = author_info.find('img')
        img_url: str = ""
        if imgurl is not None:
            img_url = imgurl.get('src')  # type: ignore
        else:
            self.log.error("Author image not found", url)

        if img_url.startswith('/'):
            img_url = self.main_url + img_url
        a = author_info.find('a')
        author_url: str = ""
        author_username: str = ""
        if a is None:
            self.log.error("Author not found", url)
        else:
            author_url = a.get('href')  # type: ignore
        if author_url.startswith('/'):
            author_url = self.main_url + author_url
            author_username = a.get_text().strip()  # type: ignore

        author = Author(url=author_url, username=author_username,
                        author_img_url=img_url)

        # Get Image class: "story-cover" > img > src
        book_img_url = soup.find(
            class_='story-cover').find('img').get('src')  # type: ignore
        if book_img_url.startswith('/'):  # type: ignore
            book_img_url = self.main_url + book_img_url  # type: ignore

        # Get Tags class: tag-items > li > a > text
        tags = []
        tag_items = soup.find(class_='tag-items')
        if tag_items is not None:
            lis = tag_items.find_all('li')  # type: ignore
            for li in lis:
                tags.append(li.find('a').get_text())

        # Get Book object
        if not isinstance(book_img_url, str):
            book_img_url = str(book_img_url)

        if not isinstance(published, str):
            published = str(published)

        book = Book(url=url, title=title, author=author, img_url=book_img_url, description=description,
                    published=published, isMature=mature, reads=reads, votes=votes, chapters=chapters,
                    total_chapters=parts, tags=tags, status=status)
        return book

    def get_story(self, story) -> Book:
        """ Get a story from wattpad
        
        Args:
            story (str): story url or story id
        
        Returns:
            Book: Book object
            
            Book object contains:
                url (str): story url
                title (str): story title
                author (Author): Author object
                img_url (str): story image url
                description (str): story description
                published (str): story published date
                isMature (bool): is story mature
                reads (int): story reads
                votes (int): story votes
                chapters (List[Chapter]): list of chapters
                total_chapters (int): total chapters
                tags (List[str]): list of tags
                status (Status): story status
        """
        return self.get_book_by_url(story)
    
    def search_books(self, query: str, limit: int = 15,start:int=0, mature: bool = True, free: bool = True, paid: bool = True,completed: bool = False, show_only_total: bool = False) -> List[Book]:  # type: ignore
        """
        Args:
            query (string): search query
            start (int, optional): start index. Defaults to 0. start to limit
            limit (int, optional): number of books to return. Defaults to 15. Max 100
            mature (bool, optional): include mature books. Defaults to True.
            free (bool, optional): include free books. Defaults to True.
            paid (bool, optional): include paid books. Defaults to True.
            completed (bool, optional): include completed books. Defaults to False.
            show_only_total (bool, optional): only return the total number of books. Defaults to False.
        Returns:
            List[Book]: returns a list of Book objects
        """
        self.log.debug("Searching for books", query)
        # options
        self.log.debug(f"Options: start: {start} limit: {limit} mature: {mature} free: {free} paid: {paid} completed: {completed}") 
        
        mature_str = "&mature=true" if mature else ""
        free_str = "&free=1" if free else ""
        paid_str = "&paid=1" if paid else ""
        completed_str = "&filter=complete" if completed else ""

        parsed_query = quote(query)
        url = f"https://www.wattpad.com/v4/search/stories?query={parsed_query}{completed_str}{mature_str}{free_str}{paid_str}&fields=stories(id,title,voteCount,readCount,commentCount,description,completed,mature,cover,url,isPaywalled,length,language(id),user(name),numParts,lastPublishedPart(createDate),promoted,sponsor(name,avatar),tags,tracking(clickUrl,impressionUrl,thirdParty(impressionUrls,clickUrls)),contest(endDate,ctaLabel,ctaURL)),chapters(url),total,tags,nexturl&limit={limit}&offset={start}"
        response = get(url)
        json_data = response.json()
        is_error = False
        er: Exception = Exception("Unknown Error")
        if not show_only_total:
            try:
                self.log.info(f"Found {json_data['total']} results")
                books = []
                for book in json_data['stories']:
                    b = Book.from_json(book)
                    books.append(b)
                return books
            except Exception as e:
                is_error = True
                er = e

        else:
            try:
                return json_data['total']
            except Exception as e:
                is_error = True
                er = e

        if is_error:
            self.log.error(
                f"[{response.status_code}] {response.text}\nError: {er}")
            self.log.info(
                f"if you can't solve this error, please report it to the developer")
            self.log.info(
                f"Or submit a bug report at https://github.com/shhossain/wattpad-scraper/issues")
            return []
    
    def search(self, query: str, limit: int = 15,start:int=0, mature: bool = True, free: bool = True, paid: bool = True,completed: bool = False, show_only_total: bool = False) -> List[Book]:
        """
        Args:
            query (string): search query
            start (int, optional): start index. Defaults to 0. start to limit
            limit (int, optional): number of books to return. Defaults to 15. Max 100
            mature (bool, optional): include mature books. Defaults to True.
            free (bool, optional): include free books. Defaults to True.
            paid (bool, optional): include paid books. Defaults to True.
            completed (bool, optional): include completed books. Defaults to False.
            show_only_total (bool, optional): only return the total number of books. Defaults to False.
        Returns:
            List[Book]: returns a list of Book objects
        """
        return self.search_books(query,limit,start,mature,free,paid,completed,show_only_total)
    

    def get_user_reading_lists(self,start=0,limit=100,username=None) -> List[ReadingList]:
        """ Get user reading lists
        Args:
            start (int, optional): start index. Defaults to 0. start to limit
            limit (int, optional): number of reading lists to return. Defaults to 100. Max 100
            username (string): username of the user to get reading lists from. Defaults to None. If None, it will use the authenticated user
        Returns:
            List[ReadingList]: returns a list of ReadingList objects
        """

        request = self.reading_list_req
        return request.get_user_reading_lists(start,limit,username)  # type: ignore

    @access_for_authenticated_user
    def create_reading_list(self, title: str) -> ReadingList:
        """ Create a reading list
        Args:
            title (string): title of the reading list

        Returns:
            ReadingList: returns a ReadingList object or False if failed
        """

        request = self.reading_list_req
        return request.create_reading_list(title)  # type: ignore

    @access_for_authenticated_user
    def create_reading_list_if_not_exists(self, title: str) -> ReadingList:
        """ Create a reading list if not exists or return the existing one
        Args:
            title (string): title of the reading list

        Returns:
            ReadingList: returns a ReadingList object or False if failed    
        """

        request = self.reading_list_req
        return request.create_reading_list_if_not_exists(title)  # type: ignore

    def get_reading_list(self, id_url_title=None, username=None) -> ReadingList:  # type: ignore
        """
        Args:
            id_url_title (required): id or url or title of the reading list.
                id: str or int
                url: str
                title: str (must provide username if not logged in)
            username (optional): username of the reading list owner

        Returns:
            ReadingList: returns a ReadingList object
        """
        request = self.reading_list_req
        return request.get_reading_list(id_url_title, username)

    @access_for_authenticated_user
    def delete_reading_list(self, reading_list: Union[str, ReadingList, int]) -> bool:
        """ Delete a reading list
        Args:
            reading_list (required): id or url or title of the reading list.
                id: str or int
                url: str
                title: str (must provide username if not logged in)

        Returns:
            bool: returns True if success
        """

        request = self.reading_list_req
        if isinstance(reading_list, ReadingList):
            reading_list = reading_list.id  # type: ignore
        elif isinstance(reading_list, int):
            reading_list = str(reading_list)
        return request.delete_reading_list(reading_list)

    @access_for_authenticated_user
    def add_to_reading_list(self, book: Union[str, Book, int, list], reading_list: Union[str, ReadingList, int],) -> Union[bool, List[bool]]:
        """ Add a book to a reading list
        Args:
            book or list of books (required): id or url or title of the book.
                id: str or int
                url: str
                title: str (must provide username if not logged in)
            reading_list (required): id or url or title of the reading list.
                id: str or int
                url: str
                title: str (must provide username if not logged in)

        Returns:
            bool: returns True if success
        """

        request = self.reading_list_req
        if isinstance(reading_list, int):
            reading_list = str(reading_list)
        if isinstance(book, int):
            book = str(book)

        return request.add_to_reading_list(book=book, reading_list=reading_list)

    @access_for_authenticated_user
    def remove_from_reading_list(self, book: Union[str, Book, int, list], reading_list: Union[str, ReadingList, int],) -> Union[bool, List[bool]]:
        """ Remove a book from a reading list
        Args:
            book or list of books (required): id or url or title of the book.
                id: str or int
                url: str
                title: str (must provide username if not logged in)
            reading_list (required): id or url or title of the reading list.
                id: str or int
                url: str
                title: str (must provide username if not logged in)

        Returns:
            bool: returns True if success
        """

        request = self.reading_list_req
        if isinstance(reading_list, int):
            reading_list = str(reading_list)
        if isinstance(book, int):
            book = str(book)

        return request.remove_from_reading_list(book=book, reading_list=reading_list)

# if __name__ == "__main__":
#     wattpad = Wattpad()
#     wattpad.search_book('harry potter')
