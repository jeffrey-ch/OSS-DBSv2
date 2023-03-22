
from typing import List
from ossdbs.electrodes.contacts import Contacts
from ossdbs.stimulation_signal import Signal
from ossdbs.volume_conductor import VolumeConductor
from abc import ABC, abstractmethod
from dataclasses import dataclass
import ngsolve
import numpy as np
import pandas as pd


@dataclass
class Impedances:

    frequencies: np.ndarray
    imdedances: np.ndarray
    contact_sets: list

    def save(self, path: str) -> None:

        data = {'frequencies [Hz]': self.frequencies}
        for index, contact_set in enumerate(self.contact_sets):
            name_1, name_2 = contact_set[0], contact_set[1]
            resistance = '_'.join(['Resistance [Ohm]', name_1, name_2])
            reactance = '_'.join(['Reactance [Ohm]', name_1, name_2])
            data.update({resistance: np.real(self.imdedances[:, index]),
                         reactance: np.imag(self.imdedances[:, index])})

        dataframe = pd.DataFrame(data)
        dataframe.to_csv(path, index=False, sep=',')


class SpectrumMode(ABC):

    @abstractmethod
    def compute(self, signal, volume_conductor, contacts) -> Impedances:
        pass


class LogarithmScanning(SpectrumMode):

    def compute(self,
                signal: Signal,
                volume_conductor: VolumeConductor,
                contacts: Contacts
                ) -> Impedances:
        frequencies = self.__frequencies(signal)
        mesh = volume_conductor.mesh.ngsolvemesh()
        settings = self.__contact_settings(contacts)
        impedances = np.zeros((len(frequencies), len(settings)), dtype=complex)

        for index, frequency in enumerate(frequencies):
            for set_index, contacts_setting in enumerate(settings):
                solution = volume_conductor.compute_solution(frequency,
                                                             contacts_setting)
                field = ngsolve.grad(solution.potential)
                curr_dens_conj = ngsolve.Conj(solution.current_density)
                power = ngsolve.Integrate(field * curr_dens_conj, mesh)
                impedances[index, set_index] = 1 / power if power else 0
                print(impedances[index])

        contact_sets = [[contact.name for contact in contacts_setting.active()]
                        for contacts_setting in settings]

        return Impedances(frequencies=frequencies,
                          imdedances=impedances,
                          contact_sets=contact_sets)

    def __frequencies(self, signal: Signal) -> List[float]:
        n_fft_frequencies = len(signal.fft_frequncies())
        n_intervalls = int(np.log10(n_fft_frequencies)) + 1
        frequencies = [0.0]
        for index in range(n_intervalls):
            interval__freq = signal.frequency * 10 ** index * np.arange(1, 10)
            frequencies.extend(interval__freq)
        return frequencies

    def __contact_settings(self, contacts: Contacts):
        return [Contacts([contact_1, contact_2] + contacts.floating())
                for index, contact_1 in enumerate(contacts.active()[:-1])
                for contact_2 in contacts.active()[index + 1:]]


class OctaveBandMode(SpectrumMode):

    class OctaveBand:

        SQRT2 = np.sqrt(2)

        def __init__(self, frequency: float) -> None:
            self.frequency = frequency

        def lower_limit(self) -> float:
            return self.frequency / self.SQRT2

        def upper_limit(self) -> float:
            return self.frequency * self.SQRT2

    def compute(self,
                signal: Signal,
                volume_conductor: VolumeConductor,
                contacts: Contacts
                ) -> Impedances:

        frequencies = signal.fft_frequncies()
        settings = self.__contact_settings(contacts)
        impedances = np.zeros((len(frequencies), len(settings)), dtype=complex)

        for index, contact_setting in enumerate(settings):
            impedances[0, index] = self.__compute_impedance(volume_conductor,
                                                            0.0,
                                                            contact_setting)

        n_octaves = int(np.log2(len(frequencies) - 1)) + 1
        for octave_band in self.__octave_bands(signal.frequency, n_octaves):
            for index, contact_setting in enumerate(settings):

                start = int(octave_band.lower_limit() / signal.frequency + 1)
                end = int(octave_band.upper_limit() / signal.frequency + 1)
                impedance = self.__compute_impedance(volume_conductor,
                                                     octave_band.frequency,
                                                     contact_setting)
                impedances[start:end, index] = impedance

        contact_sets = [[contact.name for contact in contacts_setting.active()]
                        for contacts_setting in settings]

        return Impedances(frequencies=frequencies,
                          imdedances=impedance,
                          contact_sets=contact_sets)

    def __octave_bands(self,
                       frequency: float,
                       n_octaves: int
                       ) -> List[OctaveBand]:
        octave_indices = 2 ** np.arange(0, n_octaves)
        octave_frequencies = frequency * octave_indices
        return [self.OctaveBand(freq) for freq in octave_frequencies]

    @staticmethod
    def __compute_impedance(volume_conductor: VolumeConductor,
                            frequency: float,
                            contacts: Contacts
                            ) -> float:
        solution = volume_conductor.compute_solution(frequency, contacts)
        field = ngsolve.grad(solution.potential)
        curr_dens_conj = ngsolve.Conj(solution.current_density)
        mesh = volume_conductor.mesh.ngsolvemesh()
        power = ngsolve.Integrate(field * curr_dens_conj, mesh)
        voltage = 1
        return voltage / power if power else 0

    def __contact_settings(self, contacts: Contacts):
        return [Contacts([contact_1, contact_2] + contacts.floating())
                for index, contact_1 in enumerate(contacts.active()[:-1])
                for contact_2 in contacts.active()[index + 1]]
