# Built-in modules
import numpy as np
import glob as gb
import collections as cl
import os

# BoloCalc modules
import src.band as bd
import src.detectorArray as da
import src.observationSet as ob
import src.parameter as pr
import src.units as un


class Channel:
    def __init__(self, cam, inp_dict, band_file=None):
        # Store passed parameters
        self.cam = cam
        self.inp_dict = inp_dict
        self.band_file = band_file

        # Name this channel
        self.band_id = int(self.inp_dict["Band ID"].fetch())
        self.pixel_ID = int(self.inp_dict["Band ID"].fetch())
        self.name = (self.det_arr.cam.name + str(self.band_id))

        # Store the channel parameters in a dictionary
        self._store_param_dict()

        # Elevation distribution for pixels in the camera
        elv_files = sorted(gb.glob(os.path.join(
            self.det_arr.config_dir, "elevation.txt")))
        if len(elv_files) == 0:
            self.elv_dict = None
        elif len(elv_files) > 1:
            self._log().err(
                "More than one pixel elevation distribution for camera '%s'"
                % (self.det_arr.cam.name))
            self.elv_dict = None
        else:
            self.elv_dict = self._load().elevation(elv_files[0])
            self._log().log("Using pixel elevation distribution '%s'"
                            % (camera.name, elv_file),
                            self._log().level["MODERATE"])

        # Generate the channel
        self.generate()

    # ***** Public Methods *****
    def generate(self):
        # Generate channel parameters
        self.param_vals = {}
        self.det_dict = {}
        for k in self.param_dict.keys():
            if k in self.ch_keys:
                self.param_vals[k] = self._param_samp(
                    self.param_dict[k], self.band_id)
            else:
                self.det_dict[k] = self.param_dict[k]

        # Add camera parameters
        self.camElv = camera.params["Boresight Elevation"]
        self.optCouple = camera.params["Optical Coupling"]
        self.Fnumber = camera.params["F Number"]
        self.Tb = camera.params["Bath Temp"]

        # Derived channel parameters
        self.num_det = int(self.param_vals["det_per_waf"] *
                           self.param_vals["waf_per_ot"] *
                           self.param_vals["ot"])
        if self.det_arr.cam.tel.exp.sim.fetch("ndet") is "NA":
            self.calc_det = self.num_det
        else:
            self.calc_det = self.det_arr.cam.tel.exp.sim.fetch("ndet")[0]

        # Frequencies to integrate over
        if self.band_file is not None:
            # Use defined band
            band = bd.Band(self._log(), self.band_file)
            self.loFreq = np.amin(band.freqs)
            self.hiFreq = np.amax(band.freqs)
            # Band mask edges
            self.fLo = self.loFreq
            self.fHi = self.hiFreq
        else:
            # Use wider than nominal band by 30% to cover tolerances/errors
            self.loFreq = (
                self.det_dict["bc"].getAvg() *
                (1. - 0.65*self.detectorDict["fbw"].getAvg()))
            self.hiFreq = (
                self.detectorDict["bc"].getAvg() *
                (1. + 0.65*self.detectorDict["fbw"].getAvg()))
            # Band mask edges defined using band center and fractional BW
            self.fLo = (
                self.detectorDict["bc"].getAvg() *
                (1. - 0.50*self.detectorDict["fbw"].getAvg()))
            self.fHi = (
                self.detectorDict["bc"].getAvg() *
                (1. + 0.50*self.detectorDict["fbw"].getAvg()))
        self.freqs = np.arange(
            self.loFreq, self.hiFreq+self._fres(), self._fres())
        self.nfreq = len(self.freqs)
        self.deltaF = self.freqs[-1] - self.freqs[0]

        # Band mask
        self.band_mask = (self.freqs > self.flo) * (self.freqs < self.fhi)
        self.bandDeltaF = self.fHi - self.fLo

        # Sample the pixel parameters
        self.apEff = None  # Calculated later
        self.edgeTaper = None  # Calculated later

        # Store the detector array object
        self.det_arr = da.DetectorArray(self)

        # Store the observation set object
        self.obsSet = ob.ObservationSet(self)

        # Build the element, emissivity, efficiency, and temperature arrays
        elem, emiss, effic, temp = self.cam.opt_chain.generate(self)
        self.elem = np.array(
            [[obs.elem[i] + elem + self.det_arr.detectors[i].elem
             for i in range(self.det_arr.nDet)]
             for obs in self.obsSet.observations]).astype(np.str)
        self.emiss = np.array(
            [[obs.emiss[i] + emiss + self.det_arr.detectors[i].emiss
             for i in range(self.det_arr.nDet)]
             for obs in self.obsSet.observations]).astype(np.float)
        self.effic = np.array(
            [[obs.effic[i] + effic + self.det_arr.detectors[i].effic
             for i in range(self.det_arr.nDet)]
             for obs in self.obsSet.observations]).astype(np.float)
        self.temp = np.array(
            [[obs.temp[i] + temp + self.det_arr.detectors[i].temp
             for i in range(self.det_arr.nDet)]
             for obs in self.obsSet.observations]).astype(np.float)

    # ***** Private Methods *****
    def _log(self):
        return self.cam.tel.exp.sim.log

    def _load(self):
        return self.cam.tel.exp.sim.load

    def _fres(self):
        return self.cam.tel.exp.sim.fetch("fres")

    def _cam_fetch(self, param):
        return self.cam.param_vals[param]

    def _param_samp(self, param, bandID):
        if not ("instance" in str(type(param)) or "class" in str(type(param))):
            return np.float(param)
        if self.nrealize == 1:
            return param.get_avg(band_id)
        else:
            return param.sample(band_id=band_id, nsample=1)

    def _store_param_dict(self, params):
        self.param_dict = {
            "det_per_waf": pr.Parameter(
                self._log(), "Num Det per Wafer", params["Num Det per Wafer"],
                min=0.0, max=np.inf),
            "waf_per_ot": pr.Parameter(
                self._log(), "Num Waf per OT", params["Num Waf per OT"],
                min=0.0, max=np.inf),
            "ot": pr.Parameter(
                self._log(), "Num OT", params["Num OT"],
                min=0.0, max=np.inf),
            "yield": pr.Parameter(
                self._log(), "Yield", params["Yield"],
                min=0.0, max=1.0),
            "pix_sz": pr.Parameter(
                self._log(), "Pixel Size", params["Pixel Size"],
                un.Unit("mm"), min=0.0, max=np.inf),
            "wf": pr.Parameter(
                self._log(), "Waist Factor", params["Waist Factor"],
                min=2.0, max=np.inf),
            "bc": pr.Parameter(
                self._log(), "Band Center", params["Band Center"],
                un.Unit("GHz"), min=0.0, max=np.inf),
            "fbw": pr.Parameter(
                self._log(), "Fractional BW", params["Fractional BW"],
                min=0.0, max=2.0),
            "det_eff": pr.Parameter(
                self._log(), "Det Eff", params["Det Eff"],
                min=0.0, max=1.0),
            "psat": pr.Parameter(
                self._log(), "Psat", params["Psat"],
                un.Unit("pW"), min=0.0, max=np.inf),
            "psat_fact": pr.Parameter(
                self._log(), "Psat Factor", params["Psat Factor"],
                min=0.0, max=np.inf),
            "n": pr.Parameter(
                self._log(), "Carrier Index", params["Carrier Index"],
                min=0.0, max=np.inf),
            "tc": pr.Parameter(
                self._log(), "Tc", params["Tc"],
                min=0.0, max=np.inf),
            "tc_frac": pr.Parameter(
                self._log(), "Tc Fraction", params["Tc Fraction"],
                min=0.0, max=np.inf),
            "nei": pr.Parameter(
                self._log(), "SQUID NEI", params["SQUID NEI"],
                un.Unit("pA/rtHz"), min=0.0, max=np.inf),
            "bolo_r": pr.Parameter(
                self._log(), "Bolo Resistance", params["Bolo Resistance"],
                min=0.0, max=np.inf),
            "read_frac": pr.Parameter(
                self._log(), "Read Noise Frac", params["Read Noise Frac"],
                min=0.0, max=1.0)}

        # Newly added parameters to BoloCalc
        # checked separately for backwards compatibility
        if "Flink" in params.keys():
            self.params_dict["flink"] = pr.Parameter(
                self._log(), "Flink", params["Flink"],
                min=0.0, max=np.inf)
        else:
            self.params_dict["flink"] = pr.Parameter(
                self._log(), "Flink", "NA",
                min=0.0, max=np.inf)

        if "G" in params.keys():
            self.params_dict["g"] = pr.Parameter(
                self._log(), "G", params["G"],
                un.pWtoW, min=0.0, max=np.inf)
        else:
            self.params_dict["g"] = pr.Parameter(
                self._log(), "G", "NA",
                un.pWtoW, min=0.0, max=np.inf)

        # Parameters that are the same for all detectors
        self.ch_keys = ["det_per_waf", "waf_per_ot",
                        "ot", "yield", "pix_sz", "wf"]
        return
