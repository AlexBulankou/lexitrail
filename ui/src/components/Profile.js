import React from 'react';
import '../styles/NavBar.css';

function Profile({ profileDetails, login, logOut }) {
  return (

    <div className="profile-container">
      {
        profileDetails && profileDetails.length !== 0 ? (

          <div>
            <div className="user-info">
              <img src={profileDetails.picture} alt={profileDetails.name} className='profile-avatar' />
              <div>{profileDetails.name}</div>
              <div>{profileDetails.email}</div>
            </div>

            <button onClick={logOut} className="logout-button">Logout</button>
          </div>


        ) : (
          <button className="login-button" onClick={login}>Login with Google</button>
        )
      }
    </div>

  );
}

export default Profile;
