from flask import Flask, render_template, request, jsonify, Response
from main import AccountRegistration, load_config
import logging
import queue
import threading
import time
import uuid
import json
from typing import Dict, Optional, Set, List
from dataclasses import dataclass, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# 初始化Flask应用
app = Flask(__name__)

# 加载配置
CONFIG = load_config()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class RegistrationTask:
    """注册任务数据类"""
    task_id: str
    first_name: str
    last_name: str
    username: str
    email: str
    status: str = 'pending'  # pending, running, completed, failed
    error: Optional[str] = None
    created_at: datetime = datetime.now()
    completed_at: Optional[datetime] = None
    queue_position: int = 0

class RegistrationQueue:
    def __init__(self):
        self.task_queue = queue.Queue()
        self.tasks: Dict[str, RegistrationTask] = {}
        self.active_tasks: Set[str] = set()
        self.sse_clients: Set[queue.Queue] = set()
        self.executor = ThreadPoolExecutor(max_workers=CONFIG.get('max_concurrent_tasks', 2))
        self.lock = threading.Lock()
        self._start_queue_processor()

    def _start_queue_processor(self):
        """启动队列处理器"""
        def process_queue():
            while True:
                try:
                    can_process = False
                    with self.lock:
                        # 检查是否可以处理更多任务
                        if len(self.active_tasks) < CONFIG.get('max_concurrent_tasks', 2):
                            can_process = True
                    
                    if can_process:
                        try:
                            task = self.task_queue.get(timeout=1)  # 1秒超时
                            self._process_task(task)
                        except queue.Empty:
                            pass
                    else:
                        time.sleep(1)  # 等待活动任务完成
                except queue.Empty:
                    time.sleep(0.1)  # 队列为空时短暂休眠
                except Exception as e:
                    logger.error(f"队列处理器错误: {str(e)}")
                    time.sleep(1)

        threading.Thread(target=process_queue, daemon=True).start()

    def add_task(self, task: RegistrationTask) -> str:
        """添加任务到队列"""
        with self.lock:
            self.tasks[task.task_id] = task
            self.task_queue.put(task)
            self._update_queue_positions()
            self._broadcast_queue_update()
        return task.task_id

    def _update_queue_positions(self):
        """更新队列中所有任务的位置"""
        with self.lock:
            pending_tasks = [task for task in self.tasks.values() if task.status == 'pending']
            pending_tasks.sort(key=lambda x: x.created_at)
            for i, task in enumerate(pending_tasks):
                task.queue_position = i + 1
            self._broadcast_queue_update()

    def _process_task(self, task: RegistrationTask):
        """处理单个任务"""
        def task_worker():
            try:
                with self.lock:
                    self.active_tasks.add(task.task_id)
                    task.status = 'running'
                    task.queue_position = 0
                    self._update_queue_positions()
                    self._broadcast_queue_update()

                registration = AccountRegistration()
                success, error = registration.register_account(
                    first_name=task.first_name,
                    last_name=task.last_name,
                    username=task.username,
                    email=task.email
                )

                with self.lock:
                    task.completed_at = datetime.now()
                    task.status = 'completed' if success else 'failed'
                    task.error = error
                    self.active_tasks.remove(task.task_id)
                    self._update_queue_positions()
                    self._broadcast_queue_update()

                logger.info(f"任务 {task.task_id} 完成，状态: {task.status}")
                time.sleep(5)  # 任务间隔

            except Exception as e:
                logger.error(f"处理任务时发生错误: {str(e)}")
                with self.lock:
                    task.status = 'failed'
                    task.error = str(e)
                    if task.task_id in self.active_tasks:
                        self.active_tasks.remove(task.task_id)
                    self._update_queue_positions()
                    self._broadcast_queue_update()

        self.executor.submit(task_worker)

    def add_sse_client(self) -> queue.Queue:
        """添加新的SSE客户端"""
        client_queue = queue.Queue()
        with self.lock:
            self.sse_clients.add(client_queue)
            # 在锁内立即发送当前状态，确保客户端收到最新数据
            self._send_queue_status(client_queue)
        return client_queue

    def remove_sse_client(self, client_queue: queue.Queue):
        """移除SSE客户端"""
        with self.lock:
            self.sse_clients.discard(client_queue)

    def _send_queue_status(self, client_queue: queue.Queue):
        """向单个SSE客户端发送队列状态"""
        try:
            with self.lock:
                tasks_data = []
                for task in self.tasks.values():
                    task_dict = {
                        'task_id': task.task_id,
                        'status': task.status,
                        'error': task.error,
                        'queue_position': task.queue_position,
                        'created_at': task.created_at.isoformat(),
                        'completed_at': task.completed_at.isoformat() if task.completed_at else None
                    }
                    tasks_data.append(task_dict)

                active_tasks_count = len(self.active_tasks)

            status_data = {
                'type': 'queue_update',
                'tasks': tasks_data,
                'active_tasks': active_tasks_count,
                'max_concurrent_tasks': CONFIG.get('max_concurrent_tasks', 2)
            }
            client_queue.put(json.dumps(status_data))
        except Exception as e:
            logger.error(f"发送队列状态失败: {str(e)}")
            self.remove_sse_client(client_queue)

    def _broadcast_queue_update(self):
        """向所有SSE客户端广播队列更新"""
        # 创建客户端列表的副本进行遍历
        clients = list(self.sse_clients)
        for client_queue in clients:
            try:
                self._send_queue_status(client_queue)
            except Exception:
                self.remove_sse_client(client_queue)

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            # 在锁内创建任务数据的副本
            return {
                'task_id': task.task_id,
                'status': task.status,
                'error': task.error,
                'queue_position': task.queue_position,
                'created_at': task.created_at.isoformat(),
                'completed_at': task.completed_at.isoformat() if task.completed_at else None
            }

# 创建全局队列管理器
registration_queue = RegistrationQueue()

@app.after_request
def after_request(response):
    """处理跨域请求"""
    # 只对API端点应用JSON和CORS头部
    if request.path == '/register' or request.path.startswith('/task/'):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = '*'
        response.headers['Access-Control-Allow-Methods'] = '*'
        if not response.headers.get('Content-Type'):
            response.headers['Content-Type'] = 'application/json'
    return response

@app.route('/')
def index():
    """渲染注册表单页面"""
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    """添加注册任务到队列"""
    try:
        data = request.form
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        username = data.get('username')
        email = data.get('email')

        if not all([first_name, last_name, username, email]):
            return jsonify({
                'success': False,
                'error': '所有字段都是必填的'
            })

        task = RegistrationTask(
            task_id=str(uuid.uuid4()),
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email
        )

        task_id = registration_queue.add_task(task)
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '任务已添加到队列'
        })

    except Exception as e:
        logger.error(f"添加任务时发生错误: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"添加任务失败: {str(e)}"
        })

@app.route('/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """获取任务状态"""
    status = registration_queue.get_task_status(task_id)
    if status is None:
        return jsonify({
            'success': False,
            'error': '任务不存在'
        }), 404
    
    return jsonify({
        'success': True,
        'task': status
    })

@app.route('/events')
def sse():
    """处理SSE连接"""
    def event_stream():
        client_queue = registration_queue.add_sse_client()
        try:
            while True:
                try:
                    # 等待队列更新，超时1分钟
                    data = client_queue.get(timeout=60)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    # 发送心跳保持连接
                    yield "data: {\"type\":\"heartbeat\"}\n\n"
        finally:
            registration_queue.remove_sse_client(client_queue)

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # 禁用Nginx缓冲
        }
    )

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True,
        use_reloader=True
    )
