% ENGR 315L Control Systems Lab
% Author: [Student Name]
% Date: [MM/DD/YYYY]    version 1
% Title: First-order RC charging response as the time constant varies
% File Name: [StudentName]_Lab[N]_v1.m
%
% ILLUSTRATIVE ONLY. Invented system and values; not a lab problem or answer.
% Shows: one parameter vector, a for loop filling a preallocated matrix, one
% plot call with black line styles that survive a grayscale printout, TeX
% Greek letters in labels and legend, and a printed self-check.

clc; close all; clear all;

% Code starts here:
Vs  = 12;                  % step input amplitude [V]
t   = 0:0.005:8;           % time vector [s]
TAU = [0.7 1.1 2.5];       % time constants to compare [s]

V = zeros(length(TAU), length(t));   % preallocate: one row per case
for row = 1:length(TAU)
    tau = TAU(row);
    V(row,:) = Vs * (1 - exp(-t/tau));   % .* / ./ .^ whenever t is a vector
end

% Self-check before trusting the figure: at t = tau every case must sit at
% 1 - e^-1 of the step, independent of tau.
for row = 1:length(TAU)
    [~, k] = min(abs(t - TAU(row)));
    fprintf('tau = %.1f s: V(tau)/Vs = %.4f (expect %.4f)\n', ...
            TAU(row), V(row,k)/Vs, 1 - exp(-1));
end

% One plot call, one line style per case, all black.
h = plot(t, V(1,:), '-k', ...
         t, V(2,:), '--k', ...
         t, V(3,:), '-.k');

title('Capacitor voltage v_C(t) as \tau varies');
xlabel('Time [sec]');
ylabel('v_C(t) [V]');
legend(h, {'\tau = 0.7 s', '\tau = 1.1 s', '\tau = 2.5 s'}, ...
       'Location', 'southeast');
% The figure is final as the script leaves it. Axis limits, labels, and
% styles are set here, never with the figure-window editing tools.
