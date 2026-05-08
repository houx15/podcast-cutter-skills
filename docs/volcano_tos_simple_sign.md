TosClient 在向服务端发起请求时，默认会对请求 header 里包含签名。SDK 也支持构造带签名的 URL，您可直接用该 URL 发起 HTTP 请求，也可以将该 URL 共享给第三方实现访问授权。下面给出使用预签名的 URL 上传对象，和使用预签名的URL下载示例，其他接口的使用方法以此类推。
<span id=".5L2_55So6aKE562-5ZCN55qELXVybC3kuIrkvKDlr7nosaE="></span>
## **使用预签名的 URL 上传对象**
以下代码用于预签名的 URL 向桶 `bucket-test` 中上传对象 `object-test`。
```python
import requests
import os
import tos

# 从环境变量获取 AK 和 SK 信息。
ak = os.getenv('TOS_ACCESS_KEY')
sk = os.getenv('TOS_SECRET_KEY')
endpoint = "your endpoint"
region = "your region"
bucket_name = "bucket-test"
object_key = "object-test"
content = b'test pre_signed_url put_object'
try:
    # 创建 TosClientV2 对象，对桶和对象的操作都通过 TosClientV2 实现
    client = tos.TosClientV2(ak, sk, endpoint, region)

    # 生成上传文件的签名url，有效时间为3600s
    out = client.pre_signed_url(tos.HttpMethodType.Http_Method_Put, bucket=bucket_name, key=object_key, expires=3600)
    print('签名URL的地址为', out.signed_url)
    # 使用预签名上传对象，以requests为例说明。
    out = requests.put(out.signed_url, content)
    out.close()
    # 下载对象
    get_out = client.get_object(bucket_name, object_key)
except tos.exceptions.TosClientError as e:
    # 操作失败，捕获客户端异常，一般情况为非法请求参数或网络异常
    print('fail with client error, message:{}, cause: {}'.format(e.message, e.cause))
except tos.exceptions.TosServerError as e:
    # 操作失败，捕获服务端异常，可从返回信息中获取详细错误信息
    print('fail with server error, code: {}'.format(e.code))
    # request id 可定位具体问题，强烈建议日志中保存
    print('error with request id: {}'.format(e.request_id))
    print('error with message: {}'.format(e.message))
    print('error with http code: {}'.format(e.status_code))
    print('error with ec: {}'.format(e.ec))
    print('error with request url: {}'.format(e.request_url))
except Exception as e:
    print('fail with unknown error: {}'.format(e))
```

<span id=".5L2_55So6aKE562-5ZCN55qELXVybC3kuIvovb3lr7nosaE="></span>
## **使用预签名的 URL 下载对象**
以下代码用于预签名的 URL 下载桶 `bucket-test` 中对象 `object-test`。
```python
import requests
import os
import tos
from tos import HttpMethodType

# 从环境变量获取 AK 和 SK 信息。
ak = os.getenv('TOS_ACCESS_KEY')
sk = os.getenv('TOS_SECRET_KEY')
endpoint = "your endpoint"
region = "your region"
bucket_name = "bucket-test"
object_key = "object-test"
content = b'test pre_signed_url get_object'
try:
    # 创建 TosClientV2 对象，对桶和对象的操作都通过 TosClientV2 实现
    client = tos.TosClientV2(ak, sk, endpoint, region)
    # 生成带签名的 url
    pre_signed_url_output = client.pre_signed_url(HttpMethodType.Http_Method_Get, bucket_name, object_key)
    # 使用预签名的url下载对象，以requests为例
    out = requests.get(pre_signed_url_output.signed_url)
except tos.exceptions.TosClientError as e:
    # 操作失败，捕获客户端异常，一般情况为非法请求参数或网络异常
    print('fail with client error, message:{}, cause: {}'.format(e.message, e.cause))
except tos.exceptions.TosServerError as e:
    # 操作失败，捕获服务端异常，可从返回信息中获取详细错误信息
    print('fail with server error, code: {}'.format(e.code))
    # request id 可定位具体问题，强烈建议日志中保存
    print('error with request id: {}'.format(e.request_id))
    print('error with message: {}'.format(e.message))
    print('error with http code: {}'.format(e.status_code))
    print('error with ec: {}'.format(e.ec))
    print('error with request url: {}'.format(e.request_url))
except Exception as e:
    print('fail with unknown error: {}'.format(e))
```

<span id=".5L2_55So6aKE562-5ZCN55qELXVybC3liKDpmaTlr7nosaE="></span>
## **使用预签名的 URL 删除对象**
```python
import requests
import os
import tos

# 从环境变量获取 AK 和 SK 信息。
ak = os.getenv('TOS_ACCESS_KEY')
sk = os.getenv('TOS_SECRET_KEY')
endpoint = "your endpoint"
region = "your region"
bucket_name = "bucket-test"
object_key = "object-test"
try:
    # 创建 TosClientV2 对象，对桶和对象的操作都通过 TosClientV2 实现
    client = tos.TosClientV2(ak, sk, endpoint, region)
    client.create_bucket(bucket_name)
    # 生成删除文件的签名url，有效时间为3600s
    out = client.pre_signed_url(tos.HttpMethodType.Http_Method_Delete, bucket=bucket_name, key=object_key, expires=3600)
    print('签名URL的地址为', out.signed_url)
    # 使用预签名删除对象，以requests为例说明。
    out = requests.delete(out.signed_url)
    out.close()
except tos.exceptions.TosClientError as e:
    # 操作失败，捕获客户端异常，一般情况为非法请求参数或网络异常
    print('fail with client error, message:{}, cause: {}'.format(e.message, e.cause))
except tos.exceptions.TosServerError as e:
    # 操作失败，捕获服务端异常，可从返回信息中获取详细错误信息
    print('fail with server error, code: {}'.format(e.code))
    # request id 可定位具体问题，强烈建议日志中保存
    print('error with request id: {}'.format(e.request_id))
    print('error with message: {}'.format(e.message))
    print('error with http code: {}'.format(e.status_code))
    print('error with ec: {}'.format(e.ec))
    print('error with request url: {}'.format(e.request_url))
except Exception as e:
    print('fail with unknown error: {}'.format(e))
```

<span id=".55u45YWz5paH5qGj"></span>
## **相关文档**
关于 URL 包含签名的详细信息，请参见 [URL 中包含签名](/docs/6349/129226)。



