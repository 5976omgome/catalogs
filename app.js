// =============================================
// IGNITE SCOUT - Catalog Intelligence
// Application Logic
// =============================================

(function () {
    'use strict';

    // =============================================
    // DATA
    // =============================================

    const systemLogData = [
        { time: '21:03:25', icon: 'drop', name: 'Idahams', status: 'DROP_THIRDPARTY' },
        { time: '21:03:25', icon: 'keep', name: 'BIDO', status: 'KEEP' },
        { time: '21:03:26', icon: 'drop', name: 'Masih', status: 'DROP_THIRDPARTY' },
        { time: '21:03:26', icon: 'drop', name: 'Glen Check', status: 'DROP_THIRDPARTY' },
        { time: '21:03:27', icon: 'drop', name: 'Sqweez Animal', status: 'DROP_THIRDPARTY' },
        { time: '21:03:27', icon: 'drop', name: 'Laura Misch', status: 'DROP_THIRDPARTY' },
        { time: '21:03:27', icon: 'drop', name: 'Matanza', status: 'DROP_THIRDPARTY' },
        { time: '21:03:27', icon: 'keep', name: 'jeebanoff', status: 'KEEP' },
        { time: '21:03:27', icon: 'drop', name: 'CoachDaGhost', status: 'DROP_THIRDPARTY' },
        { time: '21:03:27', icon: 'drop', name: 'Joan As Police Woman', status: 'DROP_THIRDPARTY' },
        { time: '21:03:27', icon: 'drop', name: 'The Big Moon', status: 'DROP_MAJOR' },
        { time: '21:03:27', icon: 'drop', name: 'David Sylvian', status: 'DROP_MAJOR' },
        { time: '21:03:28', icon: 'drop', name: 'Belocca', status: 'DROP_THIRDPARTY' },
        { time: '21:03:28', icon: 'keep', name: 'Arppa', status: 'KEEP' },
        { time: '21:03:28', icon: 'drop', name: 'Seba', status: 'DROP_MAJOR' },
        { time: '21:03:28', icon: 'keep', name: 'Kyle Deutsch', status: 'KEEP' },
        { time: '21:03:28', icon: 'drop', name: 'ELFL', status: 'DROP_THIRDPARTY' },
        { time: '21:03:28', icon: 'drop', name: 'Saba', status: 'DROP_THIRDPARTY' },
        { time: '21:03:28', icon: 'keep', name: 'JJ Esko', status: 'KEEP' },
        { time: '21:03:29', icon: 'keep', name: 'Enrique Lazaro', status: 'KEEP' },
        { time: '21:03:29', icon: 'drop', name: 'OG3NE', status: 'DROP_THIRDPARTY' },
        { time: '21:03:29', icon: 'keep', name: 'PRECEDE', status: 'KEEP' },
        { time: '21:03:29', icon: 'drop', name: 'Michael Cassette', status: 'DROP_THIRDPARTY' },
        { time: '21:03:29', icon: 'keep', name: 'Jryl', status: 'KEEP' },
        { time: '21:03:30', icon: 'review', name: 'Peter Bence', status: 'REVIEW' },
        { time: '21:03:31', icon: 'keep', name: 'SIMONA', status: 'KEEP' },
        { time: '21:03:31', icon: 'keep', name: 'Moon Chew', status: 'KEEP' },
        { time: '21:03:31', icon: 'keep', name: 'Zbyt Mocne 2', status: 'KEEP' },
        { time: '21:03:32', icon: 'keep', name: 'Amorf', status: 'KEEP' },
        { time: '21:03:32', icon: 'keep', name: 'D.White', status: 'KEEP' },
        { time: '21:03:33', icon: 'keep', name: 'Diana Hamilton', status: 'KEEP' },
        { time: '21:03:33', icon: 'review', name: 'Grupo Explosion', status: 'REVIEW' },
        { time: '21:03:33', icon: 'keep', name: 'OUENZA', status: 'KEEP' },
        { time: '21:03:33', icon: 'review', name: 'Fazlija', status: 'REVIEW' },
        { time: '21:03:33', icon: 'review', name: 'Sayedar', status: 'REVIEW' },
        { time: '21:03:34', icon: 'keep', name: 'Brainstorm', status: 'KEEP' },
        { time: '21:03:34', icon: 'keep', name: 'Triple One', status: 'KEEP' },
        { time: '21:03:34', icon: 'keep', name: 'Dj Parliament', status: 'KEEP' },
        { time: '21:03:34', icon: 'keep', name: 'food house', status: 'KEEP' },
        { time: '21:03:34', icon: 'keep', name: 'goethe', status: 'KEEP' },
        { time: '21:03:35', icon: 'review', name: 'Twisted Harmonies', status: 'REVIEW' },
        { time: '21:03:36', icon: 'keep', name: 'Alex1', status: 'KEEP' },
        { time: '21:03:38', icon: 'keep', name: 'Hangsung', status: 'KEEP' },
        { time: '21:03:39', icon: 'keep', name: 'YONAS', status: 'KEEP' },
        { time: '21:03:39', icon: 'keep', name: '777villain', status: 'KEEP' },
        { time: '21:03:39', icon: 'keep', name: 'Robert Tiamo', status: 'KEEP' },
        { time: '21:03:39', icon: 'keep', name: 'Rio Satrio', status: 'KEEP' },
        { time: '21:03:39', icon: 'keep', name: 'Harley Poe', status: 'KEEP' },
        { time: '21:03:40', icon: 'keep', name: 'BBY GOYARD', status: 'KEEP' },
        { time: '21:03:41', icon: 'keep', name: 'Femina', status: 'KEEP' },
        { time: '21:03:42', icon: 'review', name: 'DJ ALLAN FIALHO', status: 'REVIEW' },
        { time: '21:03:42', icon: 'keep', name: 'Leona Shijaku', status: 'KEEP' },
        { time: '21:03:42', icon: 'keep', name: 'Hopex', status: 'KEEP' },
        { time: '21:03:42', icon: 'keep', name: 'Nico Miseria', status: 'KEEP' },
        { time: '21:03:43', icon: 'keep', name: 'Elizabeth Morris', status: 'KEEP' },
        { time: '21:03:43', icon: 'keep', name: 'Mr Cho Boy', status: 'KEEP' },
        { time: '21:03:43', icon: 'keep', name: 'Raf21', status: 'KEEP' },
        { time: '21:03:44', icon: 'review', name: 'Pietju Bell', status: 'REVIEW' },
        { time: '21:03:44', icon: 'review', name: '[dunkelbunt]', status: 'REVIEW' },
        { time: '21:03:44', icon: 'keep', name: 'Vristok', status: 'KEEP' },
        { time: '21:03:45', icon: 'keep', name: 'DJ Tronky', status: 'KEEP' },
        { time: '21:03:45', icon: 'keep', name: 'Boi Bumba Garantido', status: 'KEEP' },
        { time: '21:03:45', icon: 'review', name: 'GRANi ERDi', status: 'REVIEW' },
        { time: '21:03:45', icon: 'keep', name: 'Shye', status: 'KEEP' },
        { time: '21:03:46', icon: 'keep', name: 'Daniel Glaven', status: 'KEEP' },
        { time: '21:03:46', icon: 'keep', name: 'VCL', status: 'KEEP' },
        { time: '21:03:47', icon: 'review', name: 'quiizzzmeow', status: 'REVIEW' },
        { time: '21:03:47', icon: 'review', name: 'The Trials of Cato', status: 'REVIEW' },
        { time: '21:03:47', icon: 'review', name: 'Fianru', status: 'REVIEW' },
        { time: '21:03:47', icon: 'keep', name: 'Gnawi', status: 'KEEP' },
        { time: '21:03:48', icon: 'keep', name: 'beaux', status: 'KEEP' },
        { time: '21:03:48', icon: 'keep', name: 'CIRRUS', status: 'KEEP' },
        { time: '21:03:49', icon: 'keep', name: 'Atum', status: 'KEEP' },
        { time: '21:03:49', icon: 'review', name: 'Scott Nice', status: 'REVIEW' },
    ];

    const feedData = {
        'Artists Values - 2026_06_02 - 19_50_18.csv': {
            progress: 53,
            artists: [
                {
                    name: 'Ivorian Doll', status: 'KEEP', year: 2019,
                    chartmetric: [{ value: 'Ivorian Doll', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Kosso', status: 'REVIEW', year: 2016,
                    chartmetric: [{ value: 'Kosso', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'LASER [BNL]', type: 'thirdparty' }, { value: 'kosso', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'LASER [BNL]\''
                },
                {
                    name: 'Anomalie', status: 'KEEP', year: 2013,
                    chartmetric: [{ value: 'Anomalie', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'FJAAK', status: 'KEEP', year: 2012,
                    chartmetric: [{ value: 'FJAAK', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Nessly', status: 'KEEP', year: 2013,
                    chartmetric: [{ value: 'Nessly', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Akintoye', status: 'KEEP', year: 2019,
                    chartmetric: [{ value: 'Akintoye', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Heiakim', status: 'KEEP', year: 2017,
                    chartmetric: [{ value: 'Distrokid', type: 'distributor' }],
                    itunes: [],
                    deezer: [{ value: 'heiakim', type: 'variant' }, { value: '726145 Records DK', type: 'distributor' }],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Joeyy', status: 'KEEP', year: 2018,
                    chartmetric: [{ value: 'Joeyy', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'araabMUZIK', status: 'KEEP', year: 2010,
                    chartmetric: [{ value: 'Araabmuzik, LLC', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'Araabmuzik, LLC', type: 'variant' }, { value: 'Araabmuzik LLC / EMPIRE', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Coruja', status: 'REVIEW', year: 1976,
                    chartmetric: [{ value: 'Coruja BC1', type: 'variant' }],
                    itunes: [{ value: 'Coruja Blu', type: 'variant' }, { value: 'REAL MUSIC', type: 'thirdparty' }, { value: 'Kondzilla', type: 'thirdparty' }, { value: 'BARULHENTA RECORDS', type: 'thirdparty' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: iTunes=\'REAL MUSIC\'; iTunes=\'Kondzilla\'; iTunes=\'BARULHENTA RECORDS\''
                },
                {
                    name: 'Tirri La Roca', status: 'REVIEW', year: 2021,
                    chartmetric: [{ value: 'CBM-DISCOS', type: 'thirdparty' }],
                    itunes: [{ value: 'Magenta', type: 'thirdparty' }, { value: 'Indyana Records', type: 'thirdparty' }, { value: '9387697 Records DK', type: 'distributor' }, { value: 'Tirri La Roca', type: 'variant' }, { value: 'Mueva Records', type: 'thirdparty' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: iTunes=\'Magenta\'; iTunes=\'Indyana Records\''
                },
                {
                    name: 'Smooky MarGielaa', status: 'KEEP', year: 2017,
                    chartmetric: [{ value: 'Smooky MarGielaa', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: '12th Planet', status: 'KEEP', year: 2009,
                    chartmetric: [{ value: '12th Planet', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Zheani', status: 'KEEP', year: 2018,
                    chartmetric: [{ value: 'ZHEANI', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'ZHEANI', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'V9', status: 'REVIEW', year: 2007,
                    chartmetric: [],
                    itunes: [{ value: 'Pzycco', type: 'thirdparty' }, { value: 'v9', type: 'variant' }, { value: 'Musata Music', type: 'thirdparty' }, { value: 'V9', type: 'variant' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: iTunes=\'Pzycco\'; iTunes=\'Musata Music\''
                },
                {
                    name: 'Chester See', status: 'REVIEW', year: 2008,
                    chartmetric: [{ value: 'mudhutdigital.com', type: 'thirdparty' }],
                    itunes: [],
                    deezer: [{ value: '715211 Records DK', type: 'distributor' }, { value: 'Chester See', type: 'variant' }, { value: 'mudhutdigital.com', type: 'thirdparty' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'mudhutdigital.com\'; Chartmetric=\'mudhutdigital.com\''
                },
                {
                    name: 'Rockie Fresh', status: 'REVIEW', year: 2011,
                    chartmetric: [{ value: 'Rockie Fresh', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'Rockie Fresh', type: 'variant' }, { value: 'MMG/Atlantic', type: 'thirdparty' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'MMG/Atlantic\''
                },
                {
                    name: 'TyFontaine', status: 'REVIEW', year: 2019,
                    chartmetric: [{ value: 'HighTide', type: 'thirdparty' }],
                    itunes: [],
                    deezer: [{ value: 'TyFontaine LLC', type: 'variant' }, { value: 'MNRK Records LP', type: 'thirdparty' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'MNRK Records LP\'; Chartmetric=\'HighTide\''
                },
                {
                    name: 'Cayo', status: 'REVIEW', year: 2019,
                    chartmetric: [{ value: 'Distrokid', type: 'distributor' }],
                    itunes: [],
                    deezer: [{ value: '10K Projects', type: 'thirdparty' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'10K Projects\''
                },
                {
                    name: 'Luca Lush', status: 'REVIEW', year: 2015,
                    chartmetric: [{ value: 'LUCA LUSH', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'DSR Digital', type: 'thirdparty' }, { value: 'Proximity', type: 'thirdparty' }, { value: 'LUCA LUSH', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'DSR Digital\'; Deezer=\'Proximity\''
                },
            ]
        },
        'Artists Values - 2026_05_29 - 13_51_19.csv': {
            progress: 47,
            artists: [
                {
                    name: 'Maximum Love', status: 'REVIEW', year: 2014,
                    chartmetric: [{ value: 'Maximum Love', type: 'variant' }],
                    itunes: [{ value: 'Love Nest Records', type: 'thirdparty' }, { value: 'Maximum Love', type: 'variant' }, { value: 'VAUVISION', type: 'thirdparty' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: iTunes=\'Love Nest Records\'; iTunes=\'VAUVISION\''
                },
                {
                    name: 'MC Buzzz', status: 'KEEP', year: 2018,
                    chartmetric: [{ value: 'MC Buzzz distributed by Altafonte', type: 'distributor' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Hayes & Y', status: 'KEEP', year: 2014,
                    chartmetric: [{ value: 'Hayes & Y', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Bahjat', status: 'KEEP', year: 2016,
                    chartmetric: [{ value: 'Bahjat', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'Bahjat', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Olivia C. Dacal', status: 'REVIEW', year: 2020,
                    chartmetric: [{ value: 'Olivia C. Dacal', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'Moon Beach Studios LLC', type: 'thirdparty' }, { value: 'Olivia C. Dacal', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'Moon Beach Studios LLC\''
                },
                {
                    name: 'Arppa', status: 'KEEP', year: 2019,
                    chartmetric: [{ value: 'Arppa Oy', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'PRECEDE', status: 'KEEP', year: 2011,
                    chartmetric: [{ value: 'PRECEDE', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Jryl', status: 'KEEP', year: 2019,
                    chartmetric: [{ value: 'Jryl', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'Jryl', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Scott Nice', status: 'REVIEW', year: 2016,
                    chartmetric: [{ value: 'Scott Nice', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'Scott Nice', type: 'variant' }, { value: 'George V records', type: 'thirdparty' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'George V records\''
                },
                {
                    name: 'bongor', status: 'REVIEW', year: 2017,
                    chartmetric: [{ value: 'Escape Plan Recordings', type: 'thirdparty' }],
                    itunes: [],
                    deezer: [{ value: '1288733 Records DK', type: 'distributor' }, { value: 'DJ 27 music', type: 'thirdparty' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'DJ 27 music\'; Chartmetric=\'Escape Plan Recordings\''
                },
            ]
        },
        'Artists Values - 2026_05_29 - 13_51_46.csv': {
            progress: 47,
            artists: [
                {
                    name: 'BRUNNE ROMEO', status: 'REVIEW', year: 2022,
                    chartmetric: [{ value: 'BRUNNE ROMEO', type: 'variant' }],
                    itunes: [{ value: 'BRUNNE ROMEO', type: 'variant' }, { value: 'Marina Galan', type: 'thirdparty' }, { value: 'Kraken Distribucion', type: 'thirdparty' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: iTunes=\'Marina Galan\'; iTunes=\'Kraken Distribucion\''
                },
                {
                    name: 'Ngobz', status: 'KEEP', year: 2021,
                    chartmetric: [{ value: 'Distrokid', type: 'distributor' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Alex Ricellow', status: 'REVIEW', year: 2021,
                    chartmetric: [{ value: '\u043a\u0430\u0436\u0435\u0442\u0441\u044f, \u0441\u0447\u0430\u0441\u0442\u044c\u0435', type: 'thirdparty' }],
                    itunes: [],
                    deezer: [{ value: 'Alex Ricellow', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Chartmetric=\'\u043a\u0430\u0436\u0435\u0442\u0441\u044f, \u0441\u0447\u0430\u0441\u0442\u044c\u0435\''
                },
                {
                    name: 'Benja Murano', status: 'KEEP', year: 2017,
                    chartmetric: [{ value: 'Benja Murano', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Charlie', status: 'KEEP', year: 1978,
                    chartmetric: [{ value: 'Charlie', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Samuel J', status: 'REVIEW', year: 2011,
                    chartmetric: [{ value: 'Samuel J Music', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'Ling Music Group', type: 'thirdparty' }, { value: 'Samuel J Music', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'Ling Music Group\''
                },
                {
                    name: 'Maltorian', status: 'REVIEW', year: 2019,
                    chartmetric: [{ value: 'Maltorian', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'Maltorian Music', type: 'variant' }, { value: 'Tunnel Factory', type: 'thirdparty' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'Tunnel Factory\''
                },
                {
                    name: 'BIDØ', status: 'KEEP', year: 2018,
                    chartmetric: [{ value: 'BIDØ', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Kyle Deutsch', status: 'KEEP', year: 2015,
                    chartmetric: [{ value: 'Kyle Deutsch', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Patchworks', status: 'REVIEW', year: 2004,
                    chartmetric: [{ value: 'Saigon Supersound', type: 'thirdparty' }],
                    itunes: [],
                    deezer: [{ value: 'Patchworks Productions', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Chartmetric=\'Saigon Supersound\''
                },
            ]
        },
        'Artists Values - 2026_05_29 - 13_50_28.csv': {
            progress: 52,
            artists: [
                {
                    name: 'MUSSA', status: 'REVIEW', year: 1989,
                    chartmetric: [{ value: 'MUSSA', type: 'variant' }],
                    itunes: [{ value: 'MUSSA', type: 'variant' }, { value: 'JIVE MUSSA', type: 'thirdparty' }, { value: 'Stay Busy Records', type: 'thirdparty' }, { value: 'Ministry of Sound', type: 'thirdparty' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: iTunes=\'JIVE MUSSA\'; iTunes=\'Stay Busy Records\''
                },
                {
                    name: 'Keep Shelly In Athens', status: 'KEEP', year: 2011,
                    chartmetric: [{ value: 'Keep Shelly in Athens', type: 'variant' }],
                    itunes: [{ value: 'Keep Shelly in Athens', type: 'variant' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Sheebah', status: 'REVIEW', year: 2014,
                    chartmetric: [{ value: 'SHEEBAH', type: 'variant' }],
                    itunes: [{ value: 'Ziiki Media', type: 'thirdparty' }, { value: 'Sheebah distributed by Ziiki Media', type: 'variant' }, { value: 'DCM empire', type: 'thirdparty' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: iTunes=\'Ziiki Media\'; iTunes=\'DCM empire\''
                },
                {
                    name: 'Hulya Avsar', status: 'KEEP', year: 1989,
                    chartmetric: [{ value: 'H\u00fclya Av\u015far', type: 'variant' }],
                    itunes: [{ value: 'H\u00fclya Av\u015far', type: 'variant' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Rv', status: 'KEEP', year: 2005,
                    chartmetric: [{ value: 'RV', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'El Nino de la Hipoteca', status: 'KEEP', year: 2009,
                    chartmetric: [],
                    itunes: [{ value: 'El Ni\u00f1o de la Hipoteca Records', type: 'variant' }],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Peter Bence', status: 'REVIEW', year: 2016,
                    chartmetric: [{ value: 'Peter Bence', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'PianoSphere Records', type: 'thirdparty' }, { value: 'Peter Bence', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'PianoSphere Records\''
                },
                {
                    name: 'Diana Hamilton', status: 'KEEP', year: 2005,
                    chartmetric: [{ value: 'Diana Hamilton', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'Diana Hamilton Music', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Brainstorm', status: 'KEEP', year: 1998,
                    chartmetric: [{ value: 'BrainStorm Records Company', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Triple One', status: 'KEEP', year: 2017,
                    chartmetric: [{ value: 'Triple One Records', type: 'variant' }],
                    itunes: [],
                    deezer: [],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
                {
                    name: 'Khaligraph Jones', status: 'REVIEW', year: 2009,
                    chartmetric: [{ value: 'Blu ink', type: 'thirdparty' }],
                    itunes: [],
                    deezer: [{ value: 'Coke Studio Africa', type: 'thirdparty' }, { value: 'Khaligraph Jones', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'Mixed signals. Third-party: Deezer=\'Coke Studio Africa\'; Chartmetric=\'Blu ink\''
                },
                {
                    name: 'Hangsung', status: 'KEEP', year: 2021,
                    chartmetric: [{ value: 'Hangsung', type: 'variant' }],
                    itunes: [],
                    deezer: [{ value: 'HangSung', type: 'variant' }],
                    genius: { error: true },
                    reasoning: 'All sources show artist name or known distributor'
                },
            ]
        }
    };

    // =============================================
    // RENDER FUNCTIONS
    // =============================================

    function renderSystemLog() {
        const container = document.getElementById('systemLog');
        if (!container) return;

        const html = systemLogData.map(entry => {
            const iconClass = entry.icon === 'keep' ? 'log-icon-keep' : entry.icon === 'drop' ? 'log-icon-drop' : 'log-icon-review';
            const iconChar = entry.icon === 'keep' ? '\u2713' : entry.icon === 'drop' ? '\u2717' : '\u26A0';
            const statusClass = entry.icon === 'keep' ? 'log-status-keep' : entry.icon === 'drop' ? 'log-status-drop' : 'log-status-review';

            return `<div class="log-entry"><span class="log-time">[${entry.time}]</span> <span class="${iconClass}">${iconChar}</span> <span class="log-name">${entry.name}</span> <span class="log-status ${statusClass}">\u2192 ${entry.status}</span></div>`;
        }).join('');

        container.innerHTML = html;
        container.scrollTop = container.scrollHeight;
    }

    function renderFeedTabs() {
        const container = document.getElementById('feedTabs');
        if (!container) return;

        const csvNames = Object.keys(feedData);
        const html = csvNames.map((name, i) => {
            const shortName = name.replace('Artists Values - ', '').replace('.csv', '');
            return `<button class="feed-tab${i === 0 ? ' active' : ''}" data-csv="${name}">${shortName}</button>`;
        }).join('');

        container.innerHTML = html;

        container.querySelectorAll('.feed-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                container.querySelectorAll('.feed-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                renderFeedContent(tab.dataset.csv);
            });
        });
    }

    function renderFeedContent(csvName) {
        const container = document.getElementById('feedContent');
        if (!container) return;

        const data = feedData[csvName];
        if (!data) {
            container.innerHTML = '<p style="color:var(--text-muted);padding:20px;">No data available.</p>';
            return;
        }

        const html = data.artists.map(artist => {
            const badgeClass = artist.status === 'KEEP' ? 'badge-keep' :
                artist.status === 'REVIEW' ? 'badge-review' :
                    artist.status.includes('MAJOR') ? 'badge-drop-major' : 'badge-drop-thirdparty';

            return `
                <div class="artist-card">
                    <div class="artist-card-header">
                        <span class="artist-name">${escapeHtml(artist.name)}</span>
                        <div class="artist-meta">
                            <span class="artist-year">${artist.year}</span>
                            <span class="badge ${badgeClass}">${artist.status}</span>
                        </div>
                    </div>
                    <div class="artist-readings">
                        ${renderReadingRow('CHARTMETRIC', artist.chartmetric)}
                        ${renderReadingRow('ITUNES', artist.itunes)}
                        ${renderReadingRow('DEEZER', artist.deezer)}
                        ${renderGeniusRow(artist.genius)}
                    </div>
                    <div class="artist-reasoning">${escapeHtml(artist.reasoning)}</div>
                </div>
            `;
        }).join('');

        container.innerHTML = html;
    }

    function renderReadingRow(source, values) {
        let tagsHtml = '';
        if (!values || values.length === 0) {
            tagsHtml = '<span class="reading-tag tag-none">&mdash;</span>';
        } else {
            tagsHtml = values.map(v => {
                const cls = v.type === 'variant' ? 'tag-variant' :
                    v.type === 'distributor' ? 'tag-distributor' : 'tag-thirdparty';
                const suffix = `<sup style="opacity:0.6;margin-left:2px;font-size:8px;">${v.type}</sup>`;
                return `<span class="reading-tag ${cls}">${escapeHtml(v.value)}${suffix}</span>`;
            }).join('');
        }

        return `
            <div class="reading-row">
                <span class="reading-source">${source}</span>
                <div class="reading-values">${tagsHtml}</div>
            </div>
        `;
    }

    function renderGeniusRow(genius) {
        let tagsHtml = '';
        if (!genius || genius.error) {
            tagsHtml = '<span class="reading-tag tag-social-error">API unavailable \u2014 no social data</span>';
        } else if (genius.socials && genius.socials.length > 0) {
            tagsHtml = genius.socials.map(s => {
                return `<a href="${escapeHtml(s.url)}" target="_blank" class="reading-tag tag-social">${escapeHtml(s.platform)}</a>`;
            }).join('');
        } else {
            tagsHtml = '<span class="reading-tag tag-none">No socials found</span>';
        }

        return `
            <div class="reading-row">
                <span class="reading-source">GENIUS</span>
                <div class="reading-values">${tagsHtml}</div>
            </div>
        `;
    }

    function escapeHtml(str) {
        if (!str) return '';
        const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
        return String(str).replace(/[&<>"']/g, m => map[m]);
    }

    // =============================================
    // EVENT HANDLERS
    // =============================================

    function initInstructionsModal() {
        const btn = document.getElementById('btnInstructions');
        const modal = document.getElementById('instructionsModal');
        const close = document.getElementById('modalClose');

        if (btn && modal) {
            btn.addEventListener('click', () => modal.classList.add('active'));
        }
        if (close && modal) {
            close.addEventListener('click', () => modal.classList.remove('active'));
        }
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.classList.remove('active');
            });
        }
    }

    function initVersionDropdown() {
        const btn = document.getElementById('btnVersion');
        const panel = document.getElementById('versionPanel');

        if (btn && panel) {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                panel.classList.toggle('active');
            });

            document.addEventListener('click', (e) => {
                if (!panel.contains(e.target) && e.target !== btn) {
                    panel.classList.remove('active');
                }
            });
        }
    }

    // =============================================
    // INIT
    // =============================================

    function init() {
        renderSystemLog();
        renderFeedTabs();

        const firstCsv = Object.keys(feedData)[0];
        if (firstCsv) renderFeedContent(firstCsv);

        initInstructionsModal();
        initVersionDropdown();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
