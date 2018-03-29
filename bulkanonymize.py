#!/usr/bin/env python
# -*- coding: utf-8 -*-
# quickopen.py
"""dicompyler plugin that allows quick import of DICOM data."""
# Copyright (c) 2012-2017 Aditya Panchal
# This file is part of dicompyler, released under a BSD license.
#    See the file license.txt included with this distribution, also
#    available at https://github.com/bastula/dicompyler/
#

import logging, uuid, os, threading, itertools
logger = logging.getLogger('dicompyler.quickimport')
import wx
from wx.xrc import *
from wx.lib.pubsub import pub
from dicompylercore import dicomparser
from dicompyler import util, dicomgui

import sys
def pluginProperties():
    """Properties of the plugin."""

    props = {}
    props['name'] = 'Import DICOMs to Anonymise'
    props['menuname'] = "Import DICOMs to Anonymise"
    props['description'] = "Import DICOMs to Anonymise"
    props['author'] = 'Andy Paine'
    props['version'] = "0.1.0"
    props['plugin_type'] = 'import'
    props['plugin_version'] = 1
    props['min_dicom'] = []

    return props

class plugin:

    def __init__(self, parent):

        # Initialize the import location via pubsub
        pub.subscribe(self.OnImportPrefsChange, 'general.dicom')
        pub.sendMessage('preferences.requested.values', msg='general.dicom')

        self.parent = parent

        # Setup toolbar controls
        openbmp = wx.Bitmap(util.GetResourcePath('folder_image.png'))
        self.tools = [{'label':"Bulk Anonymise", 'bmp':openbmp,
                           'shortHelp':"Bulk Anonymise",
                           'eventhandler':self.pluginMenu}]

    def pluginMenu(self, evt):
        res = XmlResource(util.GetResourcePath('dicomgui.xrc'))

        dlg = res.LoadDialog(self.parent, "DicomImporterDialog")
        dlg.Init(res)

        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.patient_data = self.GetPatientDataFromDialog(dlg)
                self.import_path = dlg.path
                # Since we have decided to use this location to import from,
                # update the location in the preferences for the next session
                # if the 'import_location_setting' is "Remember Last Used"
                if (self.import_location_setting == "Remember Last Used"):
                    pub.sendMessage('preferences.updated.value',
                        msg={'general.dicom.import_location':dlg.path})
                    pub.sendMessage('preferences.requested.values', msg='general.dicom')
            # Otherwise show an error dialog
            except (AttributeError, EOFError, IOError, KeyError) as ex:
                wx.MessageDialog(dlg, message="Something went wrong!", caption="Error selecting patient", style=wx.OK|wx.ICON_ERROR).ShowModal()
                raise
        
        dlg.Destroy()

        # Open a dialog to select the output directory
        dirDlg = wx.DirDialog(self.parent, defaultPath = self.import_path, message="Choose a folder to save the anonymized DICOM data...")
        if dirDlg.ShowModal() == wx.ID_OK:
            base_path = dirDlg.GetPath()

        dirDlg.Destroy()

        dlgProgress = guiutil.get_progress_dialog(
            wx.GetApp().GetTopWindow(),
            "Anonymizing DICOM data...")
        
        folder_counter = itertools.count()
        i = 0
        length = len(self.patient_data)
        for pat, pat_data in self.patient_data.items():
            i += 1
            wx.CallAfter(dlg.OnUpdateProgress, i, length, "Anonymising...")
            for study, study_data in pat_data.items():
                for series, series_data in study_data.items():
                    path = os.path.join(base_path, pat, study, series) 
                    if not os.path.exists(path):
                        os.makedirs(path)
                    name = str(uuid.uuid1())
                    patientid = str(uuid.uuid1())
                    self.AnonymizeDataThread(series_data, path, name, patientid, True)
        return

    def OnImportPrefsChange(self, topic, msg):
        """When the import preferences change, update the values."""
        topic = topic.split('.')
        if (topic[1] == 'import_location'):
            self.path = str(msg)
        elif (topic[1] == 'import_location_setting'):
            self.import_location_setting = msg

    def AnonymizeDataThread(self, data, path, name, patientid, privatetags):
        """Anonmyize and save each DICOM / DICOM RT file."""

        length = 0
        for key in ['rtss', 'rtplan', 'rtdose']:
            if key in data:
                length = length + 1
        if 'images' in data:
            length = length + len(data['images'])

        i = 1
        if 'rtss' in data:
            rtss = data['rtss']
            self.updateElement(rtss, 'SeriesDescription', 'RT Structure Set')
            self.updateElement(rtss, 'StructureSetDate', '19010101')
            self.updateElement(rtss, 'StructureSetTime', '000000')
            if 'RTROIObservations' in rtss:
                for item in rtss.RTROIObservations:
                    self.updateElement(item, 'ROIInterpreter', 'anonymous')
            rtss.save_as(os.path.join(path, 'rtss.dcm'))
            i = i + 1
        if 'rtplan' in data:
            rtplan = data['rtplan']
            self.updateCommonElements(rtplan, name, patientid, privatetags)
            self.updateElement(rtplan, 'SeriesDescription', 'RT Plan')
            self.updateElement(rtplan, 'RTPlanName', 'plan')
            self.updateElement(rtplan, 'RTPlanDate', '19010101')
            self.updateElement(rtplan, 'RTPlanTime', '000000')
            if 'ToleranceTables' in rtplan:
                for item in rtplan.ToleranceTables:
                    self.updateElement(item, 'ToleranceTableLabel', 'tolerance')
            if 'Beams' in rtplan:
                for item in rtplan.Beams:
                    self.updateElement(item, 'Manufacturer', 'manufacturer')
                    self.updateElement(item, 'InstitutionName', 'institution')
                    self.updateElement(item, 'InstitutionAddress', 'address')
                    self.updateElement(item, 'InstitutionalDepartmentName', 'department')
                    self.updateElement(item, 'ManufacturersModelName', 'model')
                    self.updateElement(item, 'TreatmentMachineName', 'txmachine')
            if 'TreatmentMachines' in rtplan:
                for item in rtplan.TreatmentMachines:
                    self.updateElement(item, 'Manufacturer', 'manufacturer')
                    self.updateElement(item, 'InstitutionName', 'vendor')
                    self.updateElement(item, 'InstitutionAddress', 'address')
                    self.updateElement(item, 'InstitutionalDepartmentName', 'department')
                    self.updateElement(item, 'ManufacturersModelName', 'model')
                    self.updateElement(item, 'DeviceSerialNumber', '0')
                    self.updateElement(item, 'TreatmentMachineName', 'txmachine')
            if 'Sources' in rtplan:
                for item in rtplan.Sources:
                    self.updateElement(item, 'SourceManufacturer', 'manufacturer')
                    self.updateElement(item, 'SourceIsotopeName', 'isotope')
            rtplan.save_as(os.path.join(path, 'rtplan.dcm'))
            i = i + 1
        if 'rtdose' in data:
            rtdose = data['rtdose']
            self.updateCommonElements(rtdose, name, patientid, privatetags)
            self.updateElement(rtdose, 'SeriesDescription', 'RT Dose')
            rtdose.save_as(os.path.join(path, 'rtdose.dcm'))
            i = i + 1
        if 'images' in data:
            images = data['images']
            for n, image in enumerate(images):
                self.updateCommonElements(image, name, patientid, privatetags)
                self.updateElement(image, 'SeriesDate', '19010101')
                self.updateElement(image, 'ContentDate', '19010101')
                self.updateElement(image, 'SeriesTime', '000000')
                self.updateElement(image, 'ContentTime', '000000')
                self.updateElement(image, 'InstitutionName', 'institution')
                self.updateElement(image, 'InstitutionAddress', 'address')
                self.updateElement(image, 'InstitutionalDepartmentName', 'department')
                modality = image.SOPClassUID.name.partition(' Image Storage')[0]
                image.save_as(
                    os.path.join(path, modality.lower() + '.' + str(n) + '.dcm'))
                i = i + 1

    def updateElement(self, data, element, value):
        """Updates the element only if it exists in the original DICOM data."""

        if element in data:
            data.update({element:value})

    def updateCommonElements(self, data, name, patientid, privatetags):
        """Updates the element only if it exists in the original DICOM data."""

        if len(name):
            self.updateElement(data, 'PatientsName', name)
            self.updateElement(data, 'PatientName', name)
        if len(patientid):
            self.updateElement(data, 'PatientID', patientid)
        if privatetags:
            data.remove_private_tags()
        self.updateElement(data, 'OtherPatientIDs', patientid)
        self.updateElement(data, 'OtherPatientNames', name)
        self.updateElement(data, 'InstanceCreationDate', '19010101')
        self.updateElement(data, 'InstanceCreationTime', '000000')
        self.updateElement(data, 'StudyDate', '19010101')
        self.updateElement(data, 'StudyTime', '000000')
        self.updateElement(data, 'AccessionNumber', '')
        self.updateElement(data, 'Manufacturer', 'manufacturer')
        self.updateElement(data, 'ReferringPhysiciansName', 'physician')
        self.updateElement(data, 'StationName', 'station')
        self.updateElement(data, 'NameofPhysiciansReadingStudy', 'physician')
        self.updateElement(data, 'OperatorsName', 'operator')
        self.updateElement(data, 'PhysiciansofRecord', 'physician')
        self.updateElement(data, 'ManufacturersModelName', 'model')
        self.updateElement(data, 'PatientsBirthDate', '')
        self.updateElement(data, 'PatientsSex', 'O')
        self.updateElement(data, 'PatientsAge', '000Y')
        self.updateElement(data, 'PatientsWeight', 0)
        self.updateElement(data, 'PatientsSize', 0)
        self.updateElement(data, 'PatientsAddress', 'address')
        self.updateElement(data, 'AdditionalPatientHistory', '')
        self.updateElement(data, 'EthnicGroup', 'ethnicity')
        self.updateElement(data, 'StudyID', '1')
        self.updateElement(data, 'DeviceSerialNumber', '0')
        self.updateElement(data, 'SoftwareVersions', '1.0')
        self.updateElement(data, 'ReviewDate', '19010101')
        self.updateElement(data, 'ReviewTime', '000000')
        self.updateElement(data, 'ReviewerName', 'anonymous')

    def GetPatientDataFromDialog(self, dlg):
        tree = dlg.tcPatients
        root = tree.GetRootItem()
        patients = {}
        (patient, root_cookie) = tree.GetFirstChild(root)
        while patient.IsOk():
          patient_id = str(uuid.uuid1())
          patients[patient_id] = {}
          (study, study_cookie) = tree.GetFirstChild(patient)
          while study.IsOk():
              study_id = str(uuid.uuid1())
              patients[patient_id][study_id] = {}
              (series, series_cookie) = tree.GetFirstChild(study)
              while series.IsOk():
                  series_id = str(uuid.uuid1())
                  data = tree.GetItemData(series)
                  dlg.GetPatientData(None, data['filearray'], None, true, noop)
                  patients[patient_id][study_id][series_id] = dlg.GetPatient()
                  (series, series_cookie) = tree.GetNextChild(series, series_cookie)
              (study, study_cookie) = tree.GetNextChild(patient, study_cookie)
          (patient, root_cookie) = tree.GetNextChild(root, root_cookie)
        return patients

def true():
    return True

def noop(x, y, z):
    pass
