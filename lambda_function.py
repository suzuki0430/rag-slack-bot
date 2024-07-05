import json
import os
import boto3
import requests
from botocore.config import Config

# Kendraクライアントの初期化
kendra = boto3.client("kendra", region_name="ap-northeast-1")

# Bedrockの設定
bedrock_runtime = boto3.client(
    'bedrock-runtime', config=Config(region_name='ap-northeast-1'))


def post_message_to_slack(text, channel):
    slack_token = os.getenv('SLACK_BOT_TOKEN')
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {slack_token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "channel": channel,
        "text": text
    }
    print('Payload: ', payload)
    response = requests.post(url, headers=headers, json=payload)
    return response.json()  # SlackからのレスポンスをJSONで返す


def kendra_search(question: str) -> list[dict[str, str]]:
    index_id = os.getenv('KENDRA_INDEX_ID')

    try:
        response = kendra.retrieve(
            QueryText=question,
            IndexId=index_id,
            AttributeFilter={
                "EqualsTo": {
                    "Key": "_language_code",
                    "Value": {"StringValue": "ja"},
                },
            },
        )
    except Exception as e:
        print(f"Error querying Kendra: {e}")
        return []

    print('Kendra response:', response)
    # 検索結果から上位5つを抽出
    results = response["ResultItems"][:5] if response["ResultItems"] else []

    # 検索結果の中から文章とURIのみを抽出
    extracted_results = []
    for item in results:
        content = item.get("Content")
        document_uri = item.get("DocumentURI")

        extracted_results.append(
            {
                "Content": content,
                "DocumentURI": document_uri,
            }
        )
    return extracted_results


def lambda_handler(event, context):
    slack_mention_id = os.getenv('SLACK_MENTION_ID')
    # Slackからのリクエストをパースする
    if isinstance(event['body'], str):
        slack_event = json.loads(event['body'])  # ボディが文字列の場合、JSONとして解析
    else:
        slack_event = event['body']  # ボディが既に辞書型の場合はそのまま使用
    print('slack_event', slack_event)

    # イベントタイプが 'url_verification' の場合、Slackのチャレンジ応答を処理
    if slack_event.get('type') == 'url_verification':
        return {'statusCode': 200, 'body': json.dumps({'challenge': slack_event['challenge']})}

    message_text = slack_event['event'].get('text', '')
    if slack_mention_id in message_text:
        # メンションを除いた質問を抽出
        question = message_text.replace(slack_mention_id, '').strip()
        information = kendra_search(question)
        print('information:', information)

        prompt = f"""
        \n\nSystem: あなたは株式会社OPTEMOのサービスの情報や社内規則やメンバー情報などを説明するチャットbotです。
        以下の情報を参考にして、社内のメンバーからの質問に答えてください。与えられたデータの中に質問に対する答えがない場合、もしくはわからない場合、不確かな情報は決して答えないでください。わからない場合は正直に「わかりませんでした」と答えてください。また、一度Assistantの応答が終わった場合、その後新たな質問などは出力せずに終了してください。

        {information}

        \n\nHuman: {question}

        \n\nAssistant: """

        print("Prompt:", prompt)

        try:
            response = bedrock_runtime.invoke_model(
                modelId='anthropic.claude-v2:1',
                # modelId='anthropic.claude-instant-v1',
                contentType='application/json',
                accept='*/*',
                body=json.dumps(
                    {"prompt": prompt, "max_tokens_to_sample": 600})
            )
            print("Response:", response)
            response_body = json.loads(response['body'].read().decode('utf-8'))
            completion_text = response_body.get(
                'completion', 'No completion found.')

            # Slackにメッセージを投稿
            channel_id = os.getenv('SLACK_CHANNEL_ID')
            slack_response = post_message_to_slack(completion_text, channel_id)

            print("Slack response:", slack_response)  # Slackからの応答をログ出力
            return {
                'statusCode': 200,
                'body': json.dumps('Message sent to Slack')
            }
        except Exception as e:
            print(f"Error calling Bedrock API: {e}")
            return {"error": "Unable to call Bedrock API"}

    return {
        'statusCode': 200,
        'body': json.dumps('Event received')
    }
