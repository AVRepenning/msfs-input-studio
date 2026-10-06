"""Portable app entry point and unattended smoke/diagnostic commands."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--diagnose', metavar='JSON_PATH', help='Write a Windows-controller diagnostic without opening the editor')
    parser.add_argument('--smoke-test', metavar='JSON_PATH', help='Initialize the packaged app and exit after checking the UI')
    args = parser.parse_args()
    if args.diagnose:
        from msfs_config.devices import DirectInput
        from msfs_config.catalogue import Catalogue
        from msfs_config.locations import simulator_locations
        backend = DirectInput()
        try:
            catalogue = Catalogue()
            data = {'devices': [dict(name=d.name, guid=d.instance_guid, product_id=d.product_id, vendor_id=d.vendor_id)
                                for d in backend.enumerate()], 'actions': len(catalogue.actions),
                    'verified_keys': len(catalogue.key_pairs), 'simulator_locations': simulator_locations()}
            Path(args.diagnose).write_text(json.dumps(data, indent=2), encoding='utf-8')
        finally:
            backend.close()
        return
    if args.smoke_test:
        import tkinter as tk
        from msfs_config.app import App
        root = tk.Tk()
        app = App(root, user_library=False)
        def finish():
            result = {'actions': len(app.catalogue.actions), 'rows': len(app.tree.get_children()),
                      'controller': app.device_var.get(), 'controller_open': app.controller is not None,
                      'objects': len(app.controller.objects) if app.controller else 0,
                      'profile_created': app.profile is not None, 'status': app.status.get()}
            Path(args.smoke_test).write_text(json.dumps(result, indent=2), encoding='utf-8')
            app.saved_text = app.profile.to_text() if app.profile else None
            app.close()
        root.after(2500, finish)
        root.mainloop()
        return
    from msfs_config.app import run
    run()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        import os
        log = Path(os.environ.get('LOCALAPPDATA', '.')) / 'MSFSInputStudio'
        log.mkdir(parents=True, exist_ok=True)
        details = traceback.format_exc()
        (log / 'error.log').write_text(details, encoding='utf-8')
        if not getattr(sys, 'frozen', False):
            raise
        import tkinter.messagebox
        tkinter.messagebox.showerror('MSFS Input Studio', f'The app could not start. Details were saved to:\n{log / "error.log"}')
