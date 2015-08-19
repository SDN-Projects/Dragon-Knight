# -*- codeing: utf-8 -*-
import logging
import pkgutil
import inspect
import dl_lib, dl_event
from ryu import app as ryu_app
from ryu.base import app_manager
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.base.app_manager import RyuApp, AppManager


LOG = logging.getLogger('DynamicLoader')

def deep_import(mod_name):
    mod = __import__(mod_name)
    components = mod_name.split('.')
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod

def create_context(app_name, app_cls):

    if issubclass(cls, RyuApp):
        context = self._instantiate(None, cls)
    else:
        context = cls()

    LOG.info('creating context %s', key)
    assert key not in self.contexts
    self.contexts[key] = context

class DynamicLoader(app_manager.RyuApp):

    _CONTEXTS = {
        'dl_lib': dl_lib.DynamicLoaderLib
    }

    def __init__(self, *args, **kwargs):
        super(DynamicLoader, self).__init__(*args, **kwargs)
        self.ryu_mgr = AppManager.get_instance()
        self.available_app = []
        for _, name, is_pkg in pkgutil.walk_packages(ryu_app.__path__):
            LOG.debug(
                'Find %s : %s',
                'package' if is_pkg else 'module',
                name)

            if is_pkg:
                continue

            try:
                _app_module = deep_import('ryu.app.' + name)

                for _attr_name in dir(_app_module):
                    _attr = getattr(_app_module, _attr_name)

                    if inspect.isclass(_attr) and _attr.__bases__[0] == RyuApp:
                        LOG.debug('\tFind ryu app : %s.%s', _attr.__module__, _attr.__name__)
                        _full_name = '%s.%s' % (_attr.__module__, _attr.__name__)
                        self.available_app.append((_full_name, _attr))

            except ImportError:
                LOG.debug('Import Error')


    @set_ev_cls(dl_event.EventAppListRequst, MAIN_DISPATCHER)
    def list_handler(self, req):
        res = []
        _installed_apps = self.ryu_mgr.applications

        for app_info in self.available_app:
            _cls = app_info[1]

            if _cls in \
                [obj.__class__ for obj in _installed_apps.values()]:
                res.append({'name': app_info[0], 'installed': True})

            else:
                res.append({'name': app_info[0], 'installed': False})

        rep = dl_event.EventAppListReply(req.src, res)
        self.reply_to_request(req, rep)


    @set_ev_cls(dl_event.EventAppInstall, MAIN_DISPATCHER)
    def install_handler(self, ev):
        try:
            app_id = ev.app_id
            app_cls = self.available_app[app_id][1]
            _installed_apps = self.ryu_mgr.applications

            if app_cls in \
                [obj.__class__ for obj in _installed_apps.values()]:
                # app was installed
                LOG.debug('Application already installed')

            else:
                app = self.ryu_mgr.instantiate(app_cls)
                app.start()

        except IndexError:
            LOG.debug('Can\'t find application with id %d', app_id)

        except ValueError:
            LOG.debug('ryu-app-id must be number')

        except Exception, ex:
            LOG.debug('Import error for id: %d', ev.app_id)
            raise ex


    @set_ev_cls(dl_event.EventAppUninstall, MAIN_DISPATCHER)
    def uninstall_handler(self, ev):
        app_id = ev.app_id
        app_info = self.available_app[app_id]
        # TODO: such dirty, fix it!
        app_name = app_info[0].split('.')[-1]

        if app_name in self.ryu_mgr.applications:
            app = self.ryu_mgr.applications[app_name]
            self.ryu_mgr.uninstantiate(app_name)
            app.stop()

