from gi.repository import Gtk, GObject, Gdk, GLib
import time

class BiotixMessage(Gtk.Dialog):

    def __init__(self, parent, message):
        Gtk.Dialog.__init__(self, "My Dialog", parent, 0,
                            (Gtk.STOCK_OK, Gtk.ResponseType.OK))

        self.set_default_size(150, 100)

        label = Gtk.Label(message)

        box = self.get_content_area()
        box.add(label)

        okButton = self.get_widget_for_response(response_id=Gtk.ResponseType.OK)
        okButton.set_can_default(True)
        okButton.grab_default()

        self.show_all()

class BiotixDialog(Gtk.Dialog):

    def __init__(self, parent, message):
        Gtk.Dialog.__init__(self, "My Dialog", parent, 0,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OK, Gtk.ResponseType.OK))

        self.set_default_size(150, 100)

        label = Gtk.Label(message)

        box = self.get_content_area()
        box.add(label)

        okButton = self.get_widget_for_response(response_id=Gtk.ResponseType.OK)
        okButton.set_can_default(True)
        okButton.grab_default()

        self.show_all()

class BiotixGetUserInput(Gtk.MessageDialog):

    def __init__(self, parent, inputNames, message, title=""):
        Gtk.MessageDialog.__init__(self, parent,
                          Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                          Gtk.MessageType.QUESTION,
                          Gtk.ButtonsType.OK_CANCEL,
                          message)

        self.set_title(title)
        dialogBox = self.get_content_area()
        self.textBoxesDict = dict()

        for count, name in enumerate(inputNames):

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)

            if ";" not in name:
                nameInLabel = name
                self.textBoxesDict[nameInLabel] = Gtk.Entry()
            else:
                parts = name.split(";")
                nameInLabel = parts[0]
                options = parts[1].split(",")
                self.textBoxesDict[nameInLabel] = Gtk.ComboBoxText()

                for count, item in enumerate(options):
                    self.textBoxesDict[nameInLabel].insert(count, str(count), item)

            nameLabel = Gtk.Label(nameInLabel, xalign=0)
            hbox.pack_start(nameLabel, False, True, 0)
            hbox.pack_start(self.textBoxesDict[nameInLabel], True, True, 0)

            if count == 0:
                dialogBox.pack_end(hbox, False, False, 0)
            else:
                dialogBox.pack_end(hbox, True, False, 0)

        self.show_all()

    def getAnswers(self):

        answersDict = dict()
        response = self.run()

        if response == Gtk.ResponseType.OK:

            for name in self.textBoxesDict.keys():

                if type(self.textBoxesDict[name]) ==  Gtk.Entry:
                    answersDict[name] = self.textBoxesDict[name].get_text().strip()
                elif type(self.textBoxesDict[name]) ==  Gtk.ComboBoxText:
                    tree_iter = self.textBoxesDict[name].get_active_iter()

                    if tree_iter:
                            model = self.textBoxesDict[name].get_model()
                            answersDict[name] = model[tree_iter][0].strip()
                    else:
                            answersDict[name] = ""

        elif response == Gtk.ResponseType.CANCEL:

            answersDict = None

        self.destroy()

        return answersDict

class BiotixGetCMTCredentials(Gtk.MessageDialog):

    def __init__(self, parent, message, title=""):
        Gtk.MessageDialog.__init__(self, parent,
                          Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                          Gtk.MessageType.QUESTION,
                          Gtk.ButtonsType.OK_CANCEL,
                          message)

        self.set_title(title)

        hbox1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        hbox2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)

        dialogBox = self.get_content_area()

        self.userNameBox = Gtk.Entry()
        userNameLabel = Gtk.Label("CMT user name", xalign=0)
        hbox1.pack_start(userNameLabel, False, True, 0)
        hbox1.pack_start(self.userNameBox, True, True, 0)

        self.passwordBox = Gtk.Entry()
        self.passwordBox.set_visibility(False)
        self.passwordBox.set_invisible_char("*")
        self.passwordBox.set_size_request(250,0)
        self.passwordBox.set_activates_default(True)
        passwordLabel = Gtk.Label("CMT password", xalign=0)
        hbox2.pack_start(passwordLabel, False, True, 0)
        hbox2.pack_start(self.passwordBox, True, True, 0)

        dialogBox.pack_end(hbox2, False, False, 0)
        dialogBox.pack_end(hbox1, True, False, 0)

        okButton = self.get_widget_for_response(response_id=Gtk.ResponseType.OK)
        okButton.set_can_default(True)
        okButton.grab_default()

        self.show_all()

    def getCredentials(self):
        response = self.run()
        password = self.passwordBox.get_text()
        userName = self.userNameBox.get_text()
        self.destroy()

        if (response == Gtk.ResponseType.OK) and (password != "") and (userName != ""):
            return {"password": password, "userName": userName, "timeStamp": time.time()}
        else:
            return None