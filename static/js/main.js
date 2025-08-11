document.addEventListener('DOMContentLoaded', () => {
    const themeSwitcher = document.querySelector('.theme-switcher');
    if (themeSwitcher) {
        const themeButtons = themeSwitcher.querySelectorAll('.theme-btn');
        const currentTheme = localStorage.getItem('theme') || 'daylight';
        document.documentElement.setAttribute('data-theme', currentTheme);

        themeButtons.forEach(button => {
            if (button.dataset.theme === currentTheme) {
                button.classList.add('active');
            }

            button.addEventListener('click', () => {
                const theme = button.dataset.theme;
                document.documentElement.setAttribute('data-theme', theme);
                localStorage.setItem('theme', theme);

                themeButtons.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');
            });
        });
    }
});