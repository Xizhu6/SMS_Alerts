Flask==2.3.3
Flask-SQLAlchemy==3.0.5
APScheduler==3.10.4
requests==2.31.0


from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import requests
import logging
from urllib.parse import quote

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sms_reminders.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 短信宝配置
SMSBAO_USERNAME = "xizhu"  # 请替换为您的短信宝用户名
SMSBAO_PASSWORD = "8da5b50258c24b658d6c449139a7d782"  # 请替换为您的密码MD5或ApiKey
SMSBAO_GOODSID = ""  # 产品ID（可选，如果使用专用通道则需要填写）
SMSBAO_API_URL = "http://api.smsbao.com/sms"  # 使用https://api.smsbao.com/sms 则更安全

# 数据库模型
class SMSReminder(db.Model):
    __tablename__ = 'sms_reminders'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(100), unique=True, nullable=False)
    bstudio_create_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
    sms_content = db.Column(db.String(500), nullable=False)
    target_number = db.Column(db.String(20), nullable=False)
    time = db.Column(db.DateTime, nullable=False)
    is_circulation = db.Column(db.Boolean, default=False)
    circulation_interval = db.Column(db.Integer, nullable=True)  # 间隔（分钟）
    is_sent = db.Column(db.Boolean, default=False)
    last_sent_time = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<SMSReminder {self.uuid}>'

# 创建数据库表
with app.app_context():
    db.create_all()
    logger.info("数据库表创建成功")

# API路由 - 接收智能体上传的数据
@app.route('/api/sms/create', methods=['POST'])
def create_reminder():
    """
    接收智能体上传的提醒任务
    """
    try:
        data = request.get_json()
        
        # 验证必需字段（包括uuid）
        required_fields = ['uuid', 'sms_content', 'target_number', 'time']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'message': f'缺少必需字段: {field}'
                }), 400
        
        # 从智能体获取UUID
        task_uuid = data['uuid']
        
        # 检查UUID是否已存在
        existing = SMSReminder.query.filter_by(uuid=task_uuid).first()
        if existing:
            return jsonify({
                'success': False,
                'message': f'UUID已存在: {task_uuid}'
            }), 400
        
        # 解析时间
        try:
            # 支持多种时间格式
            time_str = data['time']
            try:
                reminder_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            except:
                reminder_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'时间格式错误: {str(e)}'
            }), 400
        
        # 创建提醒任务
        reminder = SMSReminder(
            uuid=task_uuid,
            bstudio_create_time=datetime.now(),
            sms_content=data['sms_content'],
            target_number=str(data['target_number']),
            time=reminder_time,
            is_circulation=data.get('is_circulation', False),
            circulation_interval=data.get('circulation_interval')
        )
        
        db.session.add(reminder)
        db.session.commit()
        
        logger.info(f"创建新提醒任务: UUID={task_uuid}, 时间={reminder_time}")
        
        return jsonify({
            'success': True,
            'message': '提醒任务创建成功',
            'uuid': task_uuid,
            'scheduled_time': reminder_time.isoformat()
        }), 201
        
    except Exception as e:
        logger.error(f"创建提醒任务失败: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

# API路由 - 查询用户的提醒任务
@app.route('/api/sms/list/<uuid>', methods=['GET'])
def list_reminders(uuid):
    """
    查询指定用户的提醒任务
    """
    try:
        # 查询指定UUID的提醒任务
        reminder = SMSReminder.query.filter_by(uuid=uuid).first()
        
        if not reminder:
            return jsonify({
                'success': False,
                'message': '未找到该用户的提醒任务'
            }), 404
        
        result = {
            'uuid': reminder.uuid,
            'sms_content': reminder.sms_content,
            'target_number': reminder.target_number,
            'time': reminder.time.isoformat(),
            'is_circulation': reminder.is_circulation,
            'circulation_interval': reminder.circulation_interval,
            'is_sent': reminder.is_sent,
            'last_sent_time': reminder.last_sent_time.isoformat() if reminder.last_sent_time else None
        }
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
        
    except Exception as e:
        logger.error(f"查询提醒任务失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

# API路由 - 删除提醒任务
@app.route('/api/sms/delete/<uuid>', methods=['DELETE'])
def delete_reminder(uuid):
    """
    删除指定的提醒任务
    """
    try:
        reminder = SMSReminder.query.filter_by(uuid=uuid).first()
        if not reminder:
            return jsonify({
                'success': False,
                'message': '提醒任务不存在'
            }), 404
        
        db.session.delete(reminder)
        db.session.commit()
        
        logger.info(f"删除提醒任务: UUID={uuid}")
        
        return jsonify({
            'success': True,
            'message': '提醒任务删除成功'
        }), 200
        
    except Exception as e:
        logger.error(f"删除提醒任务失败: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

# 发送短信
def send_sms(uuid, sms_content, target_number):
    """
    直接调用短信宝API发送短信
    """
    try:
        # 统一短信内容格式
        formatted_content = f"【稀饭科技】同学你好,您设置的备忘消息如下:\n\n{sms_content.strip()}"
        
        # URL编码短信内容
        encoded_content = quote(formatted_content, encoding='utf-8')
        
        # 构建请求URL
        params = {
            'u': SMSBAO_USERNAME,
            'p': SMSBAO_PASSWORD,
            'm': target_number,
            'c': encoded_content
        }
        
        # 如果配置了产品ID，则添加
        if SMSBAO_GOODSID:
            params['g'] = SMSBAO_GOODSID
        
        # 构建完整URL
        param_str = '&'.join([f'{k}={v}' for k, v in params.items()])
        url = f"{SMSBAO_API_URL}?{param_str}"
        
        # 发送GET请求
        response = requests.get(url, timeout=10)
        result = response.text.strip()
        
        # 短信宝返回0表示成功
        if result == '0':
            logger.info(f"短信发送成功: UUID={uuid}, 手机号={target_number}")
            return True
        else:
            # 错误码映射
            error_map = {
                '30': '错误密码',
                '40': '账号不存在',
                '41': '余额不足',
                '43': 'IP地址限制',
                '50': '内容含有敏感词',
                '51': '手机号码不正确'
            }
            error_msg = error_map.get(result, f'未知错误码: {result}')
            logger.error(f"短信发送失败: UUID={uuid}, 手机号={target_number}, 错误={error_msg}")
            return False
            
    except Exception as e:
        logger.error(f"短信发送异常: UUID={uuid}, 错误={str(e)}")
        return False

# 定时任务 - 检查并发送提醒
def check_and_send_reminders():
    """
    检查需要发送的提醒任务并执行
    """
    with app.app_context():
        try:
            now = datetime.now()
            logger.debug(f"检查提醒任务: {now}")
            
            # 查询所有未发送的或需要循环的提醒
            reminders = SMSReminder.query.filter(
                db.or_(
                    db.and_(SMSReminder.is_sent == False, SMSReminder.time <= now),
                    db.and_(
                        SMSReminder.is_circulation == True,
                        db.or_(
                            SMSReminder.last_sent_time == None,
                            SMSReminder.last_sent_time <= now - db.func.datetime(
                                'now', f'-{SMSReminder.circulation_interval} minutes'
                            )
                        )
                    )
                )
            ).all()
            
            for reminder in reminders:
                # 检查是否应该发送
                should_send = False
                
                if not reminder.is_sent and reminder.time <= now:
                    # 首次发送
                    should_send = True
                elif reminder.is_circulation:
                    # 循环发送
                    if reminder.last_sent_time is None:
                        should_send = True
                    else:
                        next_send_time = reminder.last_sent_time + timedelta(minutes=reminder.circulation_interval)
                        if now >= next_send_time:
                            should_send = True
                
                if should_send:
                    # 发送短信
                    success = send_sms(
                        reminder.uuid,
                        reminder.sms_content,
                        reminder.target_number
                    )
                    
                    if success:
                        reminder.is_sent = True
                        reminder.last_sent_time = now
                        db.session.commit()
                        logger.info(f"提醒任务执行成功: UUID={reminder.uuid}")
                    else:
                        logger.error(f"提醒任务执行失败: UUID={reminder.uuid}")
                        
        except Exception as e:
            logger.error(f"检查提醒任务时发生错误: {str(e)}")
            db.session.rollback()

# 初始化定时调度器
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=check_and_send_reminders,
    trigger='interval',
    seconds=30,  # 每30秒检查一次
    id='check_reminders',
    name='检查并发送提醒',
    replace_existing=True
)
scheduler.start()
logger.info("定时调度器启动成功")

# 健康检查接口
@app.route('/health', methods=['GET'])
def health_check():
    """
    健康检查接口
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    }), 200

# 智能体兼容接口（支持GET/POST，参数可以在URL或body中）
@app.route('/', methods=['GET', 'POST'])
def agent_create_reminder():
    """
    智能体兼容接口 - 支持简化的参数格式
    支持GET和POST请求，参数可以在URL查询字符串或请求体中
    """
    try:
        # 获取参数（优先从JSON body，其次从URL参数）
        if request.method == 'POST' and request.is_json:
            data = request.get_json()
        else:
            # GET请求或POST的表单/URL参数
            data = request.args.to_dict() if request.args else request.form.to_dict()
        
        # 如果没有必要参数，返回API文档
        if not data.get('uuid') or not data.get('content'):
            return jsonify({
                'service': 'SMS Webhook定时提醒程序',
                'version': '1.1',
                'message': '请提供必要参数',
                'required_params': {
                    'uuid': '用户唯一标识',
                    'content': '短信内容',
                    'phone': '手机号',
                    'time': '提醒时间（HH:MM格式，如21:10）',
                    'repeat': '重复规则（可选）：每天/每周日/每周一/等'
                },
                'standard_api': 'POST /api/sms/create',
                'example': '/?uuid=test001&content=开会提醒&phone=13800138000&time=21:10&repeat=每周日'
            }), 200
        
        # 解析参数
        uuid_param = data.get('uuid')
        content = data.get('content')
        phone = data.get('phone')
        time_param = data.get('time', '09:00')  # 默认早上9点
        repeat = data.get('repeat', '')  # 重复规则
        
        # 验证必需字段
        if not uuid_param or not content or not phone:
            return jsonify({
                'success': False,
                'message': '缺少必需参数：uuid, content, phone'
            }), 400
        
        # 检查UUID是否已存在
        existing = SMSReminder.query.filter_by(uuid=uuid_param).first()
        if existing:
            return jsonify({
                'success': False,
                'message': f'UUID已存在: {uuid_param}，请使用不同的UUID'
            }), 400
        
        # 解析重复规则
        is_circulation = False
        circulation_interval = None
        
        if repeat:
            is_circulation = True
            repeat_lower = repeat.lower()
            
            if '每天' in repeat or 'daily' in repeat_lower:
                circulation_interval = 1440  # 24 * 60
            elif '每周日' in repeat or '周日' in repeat or 'sunday' in repeat_lower:
                circulation_interval = 10080  # 7 * 24 * 60
            elif '每周一' in repeat or '周一' in repeat or 'monday' in repeat_lower:
                circulation_interval = 10080
            elif '每周二' in repeat or '周二' in repeat or 'tuesday' in repeat_lower:
                circulation_interval = 10080
            elif '每周三' in repeat or '周三' in repeat or 'wednesday' in repeat_lower:
                circulation_interval = 10080
            elif '每周四' in repeat or '周四' in repeat or 'thursday' in repeat_lower:
                circulation_interval = 10080
            elif '每周五' in repeat or '周五' in repeat or 'friday' in repeat_lower:
                circulation_interval = 10080
            elif '每周六' in repeat or '周六' in repeat or 'saturday' in repeat_lower:
                circulation_interval = 10080
            elif '每周' in repeat or 'weekly' in repeat_lower:
                circulation_interval = 10080
            elif '每小时' in repeat or 'hourly' in repeat_lower:
                circulation_interval = 60
            elif '每月' in repeat or 'monthly' in repeat_lower:
                circulation_interval = 43200  # 30 * 24 * 60
            else:
                # 尝试解析数字（假设是分钟）
                try:
                    circulation_interval = int(repeat)
                except:
                    circulation_interval = 1440  # 默认每天
        
        # 解析时间（HH:MM格式）并计算下一次触发时间
        try:
            hour, minute = map(int, time_param.split(':'))
            now = datetime.now()
            
            # 计算目标时间
            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # 如果是"每周X"，需要计算到下一个对应的星期几
            if repeat and '每周' in repeat:
                weekday_map = {
                    '周一': 0, '周二': 1, '周三': 2, '周四': 3,
                    '周五': 4, '周六': 5, '周日': 6,
                    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                    'friday': 4, 'saturday': 5, 'sunday': 6
                }
                
                target_weekday = None
                for key, value in weekday_map.items():
                    if key in repeat.lower():
                        target_weekday = value
                        break
                
                if target_weekday is not None:
                    # 计算到下一个目标星期几需要的天数
                    days_ahead = target_weekday - now.weekday()
                    if days_ahead <= 0 or (days_ahead == 0 and target_time <= now):
                        days_ahead += 7
                    target_time = target_time + timedelta(days=days_ahead)
            else:
                # 如果指定时间已过，设置为明天
                if target_time <= now:
                    target_time = target_time + timedelta(days=1)
                    
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'时间格式错误，请使用HH:MM格式（如21:10）: {str(e)}'
            }), 400
        
        # 创建提醒任务
        reminder = SMSReminder(
            uuid=uuid_param,
            bstudio_create_time=datetime.now(),
            sms_content=content,
            target_number=str(phone),
            time=target_time,
            is_circulation=is_circulation,
            circulation_interval=circulation_interval
        )
        
        db.session.add(reminder)
        db.session.commit()
        
        logger.info(f"智能体创建任务: UUID={uuid_param}, 时间={target_time}, 循环={is_circulation}")
        
        return jsonify({
            'success': True,
            'message': '提醒任务创建成功',
            'uuid': uuid_param,
            'scheduled_time': target_time.isoformat(),
            'is_circulation': is_circulation,
            'circulation_interval': circulation_interval,
            'next_trigger': target_time.strftime('%Y-%m-%d %H:%M:%S')
        }), 201
        
    except Exception as e:
        logger.error(f"智能体创建任务失败: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

if __name__ == '__main__':
    try:
        logger.info("启动SMS Webhook定时提醒程序...")
        app.run(host='0.0.0.0', port=5000, debug=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("程序已关闭")

