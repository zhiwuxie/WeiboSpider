from pyspark import SparkFiles
from pyspark.sql import SparkSession
import logging
import os
from lxml import etree
import datetime
from datetime import datetime as dt
import re
from pyspark.sql.types import StructType
from pyspark.sql.types import StructField
from pyspark.sql.types import StringType
from pyspark.sql.types import Row




def main_html_parser(iterator):
    for element in iterator:
        tree_node = etree.HTML(element[3]) 
        tweet_nodes = tree_node.xpath('//div[@class="c" and @id]')
        for tweet_node in tweet_nodes:
            tweet_item = tweet_node_parser(tweet_node,element[1])
            tweet_item['crawl_time_utc'] = element[1]
            yield tweet_item

def get_tweet_id(self,tweet_url):
    if tweet_url.startswith("https://weibo.cn/comment/"):
        return tweet_url.split("/")[-1].split("?")[0]
    else:
        return ""

def tweet_node_parser(tweet_node,crawl_time_utc):
    tweet_item = {}
    # get tweet id, user id, weibo url
    tweet_repost_url = tweet_node.xpath('.//a[contains(text(),"转发[")]/@href')[0]
    user_tweet_id = re.search(r'/repost/(.*?)\?uid=(\d+)', tweet_repost_url)
    tweet_item['weibo_url'] = 'https://weibo.com/{}/{}'.format(user_tweet_id.group(2),user_tweet_id.group(1))
    tweet_item['user_id'] = user_tweet_id.group(2)
    tweet_item['_id'] = '{}'.format(user_tweet_id.group(1))
    # get created time and tool
    create_time_info_node = tweet_node.xpath('.//span[@class="ct"]')[-1]
    create_time_info = create_time_info_node.xpath('string(.)')
    if "来自" in create_time_info:
        tweet_item['created_at'],tweet_item['exact_created_at'] = time_fix(create_time_info.split('来自')[0].strip(),crawl_time_utc)
        tweet_item['tool'] = create_time_info.split('来自')[1].strip()
    else:
        tweet_item['created_at'],tweet_item['exact_created_at'] = time_fix(create_time_info.strip(),crawl_time_utc)
        tweet_item['tool'] = ""

    # get repost and like num
    like_num = tweet_node.xpath('.//a[contains(text(),"赞[")]/text()')[-1]
    tweet_item['like_num'] = int(re.search('\d+', like_num).group())

    repost_num = tweet_node.xpath('.//a[contains(text(),"转发[")]/text()')[-1]
    tweet_item['repost_num'] = int(re.search('\d+', repost_num).group())

    # get comment num
    comment_num = tweet_node.xpath(
        './/a[contains(text(),"评论[") and not(contains(text(),"原文"))]/text()')[-1]
    tweet_item['comment_num'] = int(re.search('\d+', comment_num).group())
    
    # get multi img link if exist
    multi_img_link = tweet_node.xpath('.//a[contains(text(),"组图")]/@href')
    if multi_img_link:
        tweet_item['multi_imgs_page_url'] = str(multi_img_link[-1])
        tweet_item['multi_img_ids'] = "TBD"
        tweet_item['complete_img_ids'] = False
    else:
        tweet_item['multi_imgs_page_url'] = ""
        tweet_item['multi_img_ids'] = ""
        tweet_item['complete_img_ids'] = True

    # first img link
    first_img = tweet_node.xpath('.//img[@alt="图片"]/@src')
    if first_img:
        tweet_item['multi_img_ids'] = str(first_img[0]).split("/")[-1].split(".")[0]

    # get video link
    videos = tweet_node.xpath('.//a[contains(@href,"https://m.weibo.cn/s/video/show?object_id=")]/@href')
    if videos:
        tweet_item['video_url'] = str(videos[0])
    else:
        tweet_item['video_url'] = ""

    # get map info
    map_node = tweet_node.xpath('.//a[contains(text(),"显示地图")]')
    if map_node:
        map_node = map_node[0]
        map_node_url = map_node.xpath('./@href')[0]
        map_info = re.search(r'xy=(.*?)&', map_node_url).group(1)
        tweet_item['location_map_info'] = str(map_info)
    else:
        tweet_item['location_map_info'] = ""

    # check repost information
    repost_node = tweet_node.xpath('.//a[contains(text(),"原文评论[")]/@href')
    if repost_node:
        tweet_item['retweet'] = True
        tweet_item['retweet_weibo_id'] = str(repost_node[0])
        tweet_item['retweet_user_name'] = str(tweet_node.xpath('.//span[@class="cmt"]/a/text()')[-1])
        tweet_item['retweet_user_link'] = str(tweet_node.xpath('.//span[@class="cmt"]/a/@href')[-1])
        retweet_like_num = tweet_node.xpath('.//span[@class="cmt" and contains(text(),"赞[")]/text()')[-1]
        tweet_item['retweet_like_num'] = int(re.search('\d+', retweet_like_num).group())
        retweet_comment_num = tweet_node.xpath('.//a[contains(text(),"原文评论[")]/text()')[-1]
        tweet_item['retweet_comment_num'] = int(re.search('\d+', retweet_comment_num).group())
        retweet_repost_num = tweet_node.xpath('.//span[@class="cmt" and contains(text(),"原文转发[")]/text()')[-1]
        tweet_item['retweet_repost_num'] = int(re.search('\d+', retweet_repost_num).group())
    else:
        tweet_item['retweet'] = False
        tweet_item['retweet_weibo_id'] = ""
        tweet_item['retweet_user_name'] = ""
        tweet_item['retweet_user_link'] = ""
        tweet_item['retweet_like_num'] = -1
        tweet_item['retweet_comment_num'] = -1
        tweet_item['retweet_repost_num'] = -1

    # get content and check if it is partial
    all_content_link = tweet_node.xpath('.//a[text()="全文" and contains(@href,"ckAll=1")]')
    if all_content_link:
        tweet_item['complete_content'] = False
        tweet_item['full_tweet_url'] = self.base_url + all_content_link[0].xpath('./@href')[0]
    else:
        tweet_item['complete_content'] = True

    tweet_html = etree.tostring(tweet_node, encoding='unicode')
    tweet_item['content'] = str(tweet_node.xpath('string(./div/span[@class="ctt"])'))

    # get hashtags
    hashtag_names = tweet_node.xpath('.//span[@class="ctt"]/a[contains(text(),"#")]/text()')
    if hashtag_names:
        tweet_item['hashtag_names'] = list(map(lambda x: str(x),hashtag_names))
        tweet_item['hashtag_names'] = ",".join(tweet_item['hashtag_names'])
    else:
        tweet_item['hashtag_names'] = ""

    # get content links if exist
    content_links = tweet_node.xpath('.//span[@class="ctt"]/a[not(contains(text(),"#")) and not(contains(text(),"全文"))]/@href')
    if content_links:
        tweet_item['content_links'] = list(map(lambda x: str(x),content_links))
        tweet_item['content_links'] = " ".join(tweet_item['content_links'])
    else:
        tweet_item['content_links'] = ""
    return tweet_item


def time_fix(time_string,crawl_time_utc):
    if '分钟前' in time_string:
        minutes = re.search(r'^(\d+)分钟', time_string).group(1)
        created_at = crawl_time_utc - datetime.timedelta(minutes=int(minutes))
        return created_at.strftime('%Y-%m-%d %H:%M'),False

    if '小时前' in time_string:
        minutes = re.search(r'^(\d+)小时', time_string).group(1)
        created_at = crawl_time_utc - datetime.timedelta(hours=int(minutes))
        return created_at.strftime('%Y-%m-%d %H:%M'),False

    if '今天' in time_string:
        return time_string.replace('今天', crawl_time_utc.strftime('%Y-%m-%d')),False

    if '月' in time_string:
        time_string = time_string.replace('月', '-').replace('日', '')
        time_string = str(crawl_time_utc.year) + '-' + time_string
        return time_string,False

    return time_string,True

class weiboPySparkMDBParser:

    tweet_pipeline = "{ \
            {'_id': item['_id']}, \
            { \
                '$setOnInsert': { # insert item if id not found \
                    'weibo_url' : item['weibo_url'], \
                    'created_at' : item['created_at'], \
                    'content' : item['content'], \
                    'user_id' : item['user_id'],\
                    'tool' : item['tool'],\
                    'multi_imgs' : item['multi_imgs'],\
                    'image_url' : item['image_url'],\
                    'video_url' : item['video_url'],\
                    'location_map_info' : item['location_map_info'],\
                    'retweet' : item['retweet'],\
                    'origin_weibo' : item['origin_weibo']\
                },\
                '$push': {\
                    'like_num': item['like_num'],\
                    'repost_num': item['repost_num'],\
                    'comment_num': item['comment_num'],\
                    'crawl_time_utc': item['crawl_time_utc']\
                }\
            },\
            upsert=True\
    }"



    def __init__(self):
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
        spark_builder = (
            SparkSession
            .builder
            .master("local")
            .config('spark.mongodb.input.uri', 'mongodb://127.0.0.1:27017/Sina2')
            .config('spark.mongodb.output.uri', 'mongodb://127.0.0.1:27017/Sina2')
            .appName("Weibo Pyspark MongoDB Parser"))
        self.spark = spark_builder.getOrCreate() # get spark session
        logging.info("Spark Session Created")


    def findPotentialUser(self):
        df = self.spark.read.format("com.mongodb.spark.sql.DefaultSource").option("uri","mongodb://127.0.0.1:27017/Sina2.SearchPageRaw").load()
        df.show(2)
        rdd = df.rdd
        transformed = rdd.mapPartitions(main_html_parser)
        logging.info(transformed.take(2))
        transformed_df = transformed.toDF()
        transformed_df.write.format("mongo").mode("append").option("database","SWtest").option("collection", "test1").save()

    

if __name__ == "__main__":
    parser = weiboPySparkMDBParser()
    parser.findPotentialUser()
    logging.info("END")

