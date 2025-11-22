from pymongo import MongoClient
from config import Config


def connect_twitter_db():
    config = Config()
    client = MongoClient(config.get_mongo_url)
    db_twitter = client.twitter
    return db_twitter

if __name__ == '__main__':
    db = connect_twitter_db()

    # 获取集合
    users_collection = db.users

    # 插入单个文档
    user_data = {
        "name": "张三",
        "age": 25,
        "email": "zhangsan@example.com",
        "city": "北京",
        "hobbies": ["阅读", "游泳", "编程"],
        "created_at": "2024-01-01"
    }

    result = users_collection.insert_one(user_data)
    print(f"插入成功，文档ID: {result.inserted_id}")

    # 插入多个文档
    users_list = [
        {"name": "李四", "age": 30, "city": "上海"},
        {"name": "王五", "age": 28, "city": "广州"},
        {"name": "赵六", "age": 35, "city": "深圳"}
    ]

    result = users_collection.insert_many(users_list)
    print(f"插入了 {len(result.inserted_ids)} 个文档")